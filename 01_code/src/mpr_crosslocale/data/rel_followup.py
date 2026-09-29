"""Validate and transfer the frozen, generated REL O/R/C/F dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import urlopen

LANGUAGES = ("en", "zh", "th", "ru")
CONDITIONS = ("O", "R", "C", "F")
FIELDS = ("question_stem", "A", "B", "C", "D")
DATA_DIR = "data/rel_all_366"
BUNDLE_MANIFEST = "bundle_manifest.json"
TRANSFER_FILES = (
    "conditions_4lang.jsonl",
    "quartets_4lang.jsonl",
    "reference_mappings.jsonl",
    "manifest_366_4lang.json",
    "assets_required.json",
    "config.json",
    "generation_report.json",
    "source_issues.json",
    "README_KO.md",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def safe_path(root: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or parts.is_absolute() or ".." in parts.parts:
        raise ValueError(f"Unsafe relative path: {name!r}")
    target = root.joinpath(*parts.parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes data root: {name!r}")
    return target


def text_fields(row: dict) -> dict:
    return {"question_stem": row["question_stem"], **row["options"]}


def validate_dataset(root: Path, *, images: bool = False, decode_images: bool = False) -> tuple:
    """Check all quartets and reconstruct every field from immutable reference spans."""
    rows = read_jsonl(root / DATA_DIR / "conditions_4lang.jsonl")
    mappings = read_jsonl(root / DATA_DIR / "reference_mappings.jsonl")
    maps = {m["parallel_id"]: m for m in mappings}
    if len(maps) != len(mappings) or not maps:
        raise ValueError("Reference mappings must contain unique, nonempty item IDs")
    groups = defaultdict(dict)
    image_names = set()
    for row in rows:
        pid, q, g, c = (
            row[k] for k in ("parallel_id", "query_language", "gui_language", "condition")
        )
        if q not in LANGUAGES or g not in LANGUAGES or c not in CONDITIONS:
            raise ValueError(f"Unknown language/condition: {pid}, {q}, {g}, {c}")
        if pid not in maps or c in groups[pid, q, g]:
            raise ValueError(f"Missing mapping or duplicate condition: {pid}, {q}, {g}, {c}")
        groups[pid, q, g][c] = row
        if row["pair_id"] != f"{pid}::{q}::{g}" or row["matched"] != (q == g):
            raise ValueError(f"Inconsistent pair identity: {row['pair_id']}")
        if row["primary_analysis"] != (q != g) or row["dimension"] != "rel":
            raise ValueError("Invalid analysis population/dimension")
        if row["text_dependency"] not in ("dependent", "independent"):
            raise ValueError("Invalid text-dependency group")
        if row["option_order"] != list("ABCD") or row["gold_answer"] not in "ABCD":
            raise ValueError("Invalid answer or option order")
        if set(row["options"]) != set("ABCD"):
            raise ValueError("Missing/extra options")
        if row["eligible_without_source_adjudication"] != (row.get("source_issue") is None):
            raise ValueError("Source issue and eligibility disagree")
        image = safe_path(root, row["image_path"])
        if not row["image_path"].startswith("assets/images/"):
            raise ValueError("Image is outside assets/images")
        image_names.add(row["image_path"])
        if images and (not image.is_file() or not image.stat().st_size):
            raise ValueError(f"Missing/empty image: {image}")
        expected_context, expected_refs = {"O": (q, q), "R": (q, g), "C": (g, q), "F": (g, g)}[c]
        if (row["context_language"], row["reference_language"]) != (
            expected_context,
            expected_refs,
        ):
            raise ValueError("Condition context/reference languages disagree")
        mapping = maps[pid]
        actual = text_fields(row)
        for field in FIELDS:
            base = mapping["fields"][expected_context][field]
            targets = {s["ref_id"]: s["text"] for s in mapping["spans"][expected_refs][field]}
            spans = sorted(mapping["spans"][expected_context][field], key=lambda s: s["start"])
            pieces, cursor = [], 0
            for span in spans:
                start, end = span["start"], span["end"]
                if not cursor <= start < end <= len(base) or base[start:end] != span["text"]:
                    raise ValueError(f"Invalid span: {pid}/{expected_context}/{field}")
                pieces.extend((base[cursor:start], targets[span["ref_id"]]))
                cursor = end
            pieces.append(base[cursor:])
            if actual[field] != "".join(pieces) or not actual[field].strip():
                raise ValueError(f"Reference/context reconstruction failed: {pid}/{q}/{g}/{c}")
        combined = (
            actual["question_stem"]
            + " "
            + " ".join(f"{option}: {actual[option]}" for option in "ABCD")
        )
        if row["question"] != combined:
            raise ValueError("Combined question does not match question/options")
    unique_calls = 0
    for pid in maps:
        for q in LANGUAGES:
            for g in LANGUAGES:
                quartet = groups[pid, q, g]
                if set(quartet) != set(CONDITIONS):
                    raise ValueError(f"Incomplete quartet: {pid}/{q}/{g}")
                for field in ("image_path", "gold_answer", "text_dependency", "state_key"):
                    if len({r[field] for r in quartet.values()}) != 1:
                        raise ValueError(f"Quartet changes {field}: {pid}/{q}/{g}")
                seen = {}
                for c in CONDITIONS:
                    row = quartet[c]
                    first = seen.setdefault(row["question"], c)
                    if row["equivalent_to_condition"] != first:
                        raise ValueError("Incorrect condition equivalence metadata")
                unique_calls += len(seen)
                if q == g and len(seen) != 1:
                    raise ValueError("Matched quartet must be identical")
                reverse = groups[pid, g, q]
                for a, b in zip(CONDITIONS, ("F", "C", "R", "O")):
                    if quartet[a]["question"] != reverse[b]["question"]:
                        raise ValueError("Reverse-pair text symmetry failed")
    if len(rows) != len(maps) * 64:
        raise ValueError("Unexpected total row count")
    if decode_images:
        from PIL import Image

        for name in sorted(image_names):
            with Image.open(safe_path(root, name)) as image:
                image.verify()
            with Image.open(safe_path(root, name)) as image:
                image.load()
    bad = [r for r in rows if not r["eligible_without_source_adjudication"]]
    methods = Counter(method for m in mappings for method in set(m["methods"].values()))
    report = {
        "schema": "rel-followup-audit-v1",
        "structural_checks_passed": True,
        "items": len(maps),
        "rows": len(rows),
        "language_pairs": len(groups),
        "items_by_dependency": dict(
            Counter(groups[pid, "en", "en"]["O"]["text_dependency"] for pid in maps)
        ),
        "mismatch_rows": sum(r["primary_analysis"] for r in rows),
        "unique_inferences_within_pairs": unique_calls,
        "source_issue_rows": len(bad),
        "source_issue_pairs": len({r["pair_id"] for r in bad}),
        "source_issue_items": sorted({r["parallel_id"] for r in bad}),
        "R_equals_O_mismatch_pairs": sum(
            q != g and v["R"]["question"] == v["O"]["question"] for (_, q, g), v in groups.items()
        ),
        "method_item_counts": dict(methods),
        "image_files": len(image_names),
        "images_present_checked": images,
        "images_decoded_checked": decode_images,
        "conditions_sha256": digest(root / DATA_DIR / "conditions_4lang.jsonl"),
        "review_scope": "Structural/reference reconstruction checks and known source-issue review; "
        "not exhaustive semantic or screenshot-label adjudication.",
        "human_reviewed": False,
        "screenshot_verified_all": False,
        "source_issue_policy": "Infer all rows; exclude flagged full quartets from primary analysis.",
    }
    return rows, report


def verify_bundle(root: Path, *, images: bool = False) -> dict:
    manifest = json.loads((root / BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    if manifest["schema"] != "rel-followup-bundle-v1":
        raise ValueError("Unknown bundle schema")
    for entry in manifest["files"] + (manifest["images"] if images else []):
        path = safe_path(root, entry["path"])
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or digest(path) != entry["sha256"]
        ):
            raise ValueError(f"Bundle checksum mismatch: {entry['path']}")
    return manifest


def pack(root: Path, output: Path, lock_out: Path, include_images: bool = False) -> dict:
    rows, report = validate_dataset(root, images=True, decode_images=True)
    files = []
    for name in TRANSFER_FILES:
        relative = f"{DATA_DIR}/{name}"
        path = safe_path(root, relative)
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)})
    generation = json.loads(
        (root / DATA_DIR / "generation_report.json").read_text(encoding="utf-8")
    )
    source = generation["source"]
    image_entries = []
    for name in sorted({r["image_path"] for r in rows}):
        path = safe_path(root, name)
        asset = name.removeprefix("assets/images/")
        url = (
            f"https://huggingface.co/datasets/{source['hf_repo']}/resolve/"
            f"{source['hf_revision']}/{quote(asset, safe='/')}"
        )
        image_entries.append(
            {"path": name, "bytes": path.stat().st_size, "sha256": digest(path), "url": url}
        )
    manifest = {
        "schema": "rel-followup-bundle-v1",
        "files": files,
        "images": image_entries,
        "source": source,
        "audit": report,
        "includes_images": include_images,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with tarfile.open(temporary, "w:gz", compresslevel=6) as archive:
        import io

        payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        info = tarfile.TarInfo(BUNDLE_MANIFEST)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
        for entry in files + (image_entries if include_images else []):
            archive.add(safe_path(root, entry["path"]), arcname=entry["path"], recursive=False)
    temporary.replace(output)
    lock = {
        "schema": "rel-followup-lock-v1",
        "bundle_name": output.name,
        "bundle_sha256": digest(output),
        "bundle_bytes": output.stat().st_size,
        "conditions_sha256": report["conditions_sha256"],
        "audit": report,
        "source": source,
        "includes_images": include_images,
    }
    write_json(lock_out, lock)
    return lock


def unpack(bundle: Path, root: Path, lock_path: Path) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if digest(bundle) != lock["bundle_sha256"]:
        raise ValueError("Archive SHA-256 differs from the published dataset lock")
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(set(names)) != len(names) or any(not m.isfile() for m in members):
            raise ValueError("Archive has duplicate paths or non-file entries")
        for member in members:
            safe_path(root, member.name)
        manifest = json.load(archive.extractfile(BUNDLE_MANIFEST))
        entries = manifest["files"] + (manifest["images"] if manifest["includes_images"] else [])
        allowed = {e["path"]: e for e in entries}
        if set(names) != set(allowed) | {BUNDLE_MANIFEST}:
            raise ValueError("Unexpected archive entries")
        for member in members:
            target = safe_path(root, member.name)
            expected = allowed.get(member.name)
            if target.exists():
                if member.name == BUNDLE_MANIFEST:
                    if json.loads(target.read_text(encoding="utf-8")) != manifest:
                        raise ValueError("Refusing to overwrite a different dataset manifest")
                elif digest(target) != expected["sha256"]:
                    raise ValueError(f"Refusing to overwrite different data: {member.name}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".tmp")
            with archive.extractfile(member) as source, temporary.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            if expected and digest(temporary) != expected["sha256"]:
                temporary.unlink()
                raise ValueError(f"Bad extracted checksum: {member.name}")
            temporary.replace(target)
    manifest = verify_bundle(root, images=manifest["includes_images"])
    if manifest["audit"]["conditions_sha256"] != lock["conditions_sha256"]:
        raise ValueError("Conditions disagree with dataset lock")
    return manifest["audit"]


def fetch_images(root: Path, workers: int) -> dict:
    manifest = verify_bundle(root)
    source = manifest["source"]
    prefix = f"https://huggingface.co/datasets/{source['hf_repo']}/resolve/{source['hf_revision']}/"

    def fetch(entry):
        path = safe_path(root, entry["path"])
        expected_url = prefix + quote(entry["path"].removeprefix("assets/images/"), safe="/")
        if entry["url"] != expected_url or not expected_url.startswith("https://huggingface.co/"):
            raise ValueError("Unexpected image URL")
        if (
            path.is_file()
            and path.stat().st_size == entry["bytes"]
            and digest(path) == entry["sha256"]
        ):
            return "cached"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".download")
        for attempt in range(3):
            try:
                with urlopen(expected_url, timeout=60) as response, temporary.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
                if digest(temporary) != entry["sha256"]:
                    raise ValueError(f"Downloaded image checksum mismatch: {entry['path']}")
                temporary.replace(path)
                return "downloaded"
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    counts = Counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, result in enumerate(executor.map(fetch, manifest["images"]), 1):
            counts[result] += 1
            if index % 50 == 0:
                print(f"Images verified: {index}/{len(manifest['images'])}", flush=True)
    verify_bundle(root, images=True)
    return dict(counts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "pack", "unpack", "fetch-images", "verify"))
    parser.add_argument("--data-root", type=Path, default=Path("followup_rel_4lang"))
    parser.add_argument(
        "--bundle", type=Path, default=Path("followup_rel_4lang/bundles/rel_all_366.tar.gz")
    )
    parser.add_argument("--lock", type=Path, default=Path("followup_rel_4lang/dataset_lock.json"))
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--include-images", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.action == "pack":
        result = pack(args.data_root, args.bundle, args.lock, args.include_images)
    elif args.action == "unpack":
        result = unpack(args.bundle, args.data_root, args.lock)
    elif args.action == "fetch-images":
        if not 1 <= args.workers <= 16:
            parser.error("--workers must be between 1 and 16")
        result = fetch_images(args.data_root, args.workers)
    elif args.action == "verify":
        result = verify_bundle(args.data_root, images=True)["audit"]
    else:
        _, result = validate_dataset(args.data_root, images=True, decode_images=True)
    if args.report_out:
        write_json(args.report_out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
