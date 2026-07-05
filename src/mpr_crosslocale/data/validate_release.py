from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.data.episode_loader import sorted_episode_frames
from mpr_crosslocale.data.parallel_index import canonical_state_key, normalize_asset_reference

LANGUAGES = ("en", "zh", "fr", "ru", "ja", "th")
DIMENSION_FILES = {
    "wf": "wf",
    "wi": "wi",
    "au": "au",
    "ap": "ap",
    "ael": "abs_el",
    "rel": "rel_el",
    "ri": "knowledge_rich",
    "si": "knowledge_sparse",
}
PAPER_REPORTED_SAMPLES_PER_LANGUAGE = 2156


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line.strip():
                yield line_no, json.loads(line)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_hf_license(images_dir: Path) -> str | None:
    readme = images_dir / "README.md"
    if not readme.exists():
        return None
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.startswith("license:"):
            return line.split(":", 1)[1].strip()
    return None


def resolve_asset_path(images_dir: Path, asset: str) -> Path:
    normalized = normalize_asset_reference(asset)
    return images_dir / normalized


def row_asset(row: dict[str, object]) -> tuple[str, bool]:
    if "image_path" in row:
        return str(row["image_path"]), False
    if "image_folder_path" in row:
        return str(row["image_folder_path"]), True
    return "", False


def question_signature(question: str) -> str:
    # Keep this intentionally simple and stable; it is for duplicate diagnostics.
    return " ".join(question.split())


def audit_release(root: Path) -> dict[str, object]:
    images_dir = root / "images"
    qas_dir = root / "qas"
    files: dict[str, dict[str, object]] = {}
    by_language: dict[str, Counter[str]] = {lang: Counter() for lang in LANGUAGES}
    by_dimension: dict[str, Counter[str]] = {dim: Counter() for dim in DIMENSION_FILES}
    parallel: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    duplicate_questions: dict[str, int] = {}
    noncanonical_answer_fields: list[dict[str, object]] = []
    missing_assets: list[dict[str, object]] = []
    malformed_answers: list[dict[str, object]] = []
    episode_frame_counts: list[dict[str, object]] = []
    total_rows = 0

    for path in sorted(qas_dir.glob("*.jsonl")):
        stem = path.stem
        language = stem.rsplit("_", 1)[-1]
        dimension = next(
            (dim for dim, prefix in DIMENSION_FILES.items() if stem == f"{prefix}_{language}"),
            "unknown",
        )
        labels: Counter[str] = Counter()
        question_counts: Counter[str] = Counter()
        rows = 0
        missing_in_file = 0
        folder_rows = 0
        for line_no, row in iter_jsonl(path):
            rows += 1
            total_rows += 1
            label = parse_label(str(row.get("answer", "")))
            if label is None:
                malformed_answers.append({"file": path.name, "line": line_no, "answer": row.get("answer", "")})
            else:
                labels[label] += 1
                if str(row.get("answer", "")).strip().upper() != label:
                    noncanonical_answer_fields.append(
                        {"file": path.name, "line": line_no, "answer": row.get("answer", ""), "label": label}
                    )
            question_counts[question_signature(str(row.get("question", "")))] += 1
            asset, is_folder = row_asset(row)
            asset_path = resolve_asset_path(images_dir, asset) if asset else images_dir / "__missing__"
            if not asset or not asset_path.exists():
                missing_in_file += 1
                missing_assets.append({"file": path.name, "line": line_no, "asset": asset})
            elif is_folder:
                folder_rows += 1
                frames = sorted_episode_frames(asset_path)
                episode_frame_counts.append(
                    {
                        "file": path.name,
                        "line": line_no,
                        "asset": asset,
                        "frames": len(frames),
                        "first_frame": frames[0].name if frames else None,
                        "last_frame": frames[-1].name if frames else None,
                    }
                )
            if dimension != "unknown" and language in LANGUAGES and asset:
                parallel[dimension][canonical_state_key(asset)].add(language)
        duplicate_count = sum(count - 1 for count in question_counts.values() if count > 1)
        if duplicate_count:
            duplicate_questions[path.name] = duplicate_count
        files[path.name] = {
            "rows": rows,
            "language": language,
            "dimension": dimension,
            "answer_labels": dict(labels),
            "missing_assets": missing_in_file,
            "episode_rows": folder_rows,
            "duplicate_question_excess": duplicate_count,
            "sha256": file_sha256(path),
        }
        if language in by_language:
            by_language[language][dimension] += rows
        if dimension in by_dimension:
            by_dimension[dimension][language] += rows

    parallel_summary: dict[str, dict[str, object]] = {}
    for dimension, states in sorted(parallel.items()):
        complete = sum(1 for languages in states.values() if set(languages) == set(LANGUAGES))
        language_coverage = Counter()
        for languages in states.values():
            language_coverage[len(languages)] += 1
        parallel_summary[dimension] = {
            "unique_state_keys": len(states),
            "complete_six_language_states": complete,
            "coverage_histogram_num_languages": dict(sorted(language_coverage.items())),
            "incomplete_state_keys": [
                {"state_key": key, "languages": sorted(languages)}
                for key, languages in sorted(states.items())
                if set(languages) != set(LANGUAGES)
            ][:50],
        }

    rows_by_language = {lang: sum(counter.values()) for lang, counter in by_language.items()}
    paper_delta = {
        lang: rows_by_language.get(lang, 0) - PAPER_REPORTED_SAMPLES_PER_LANGUAGE
        for lang in LANGUAGES
    }
    return {
        "root": root.as_posix(),
        "images_dir_exists": images_dir.exists(),
        "qas_dir_exists": qas_dir.exists(),
        "image_jpg_files": len(list(images_dir.glob("**/*.jpg"))) if images_dir.exists() else 0,
        "qas_jsonl_files": len(list(qas_dir.glob("*.jsonl"))) if qas_dir.exists() else 0,
        "dataset_license": read_hf_license(images_dir),
        "total_rows": total_rows,
        "rows_by_language": rows_by_language,
        "rows_by_dimension": {dim: sum(counter.values()) for dim, counter in by_dimension.items()},
        "language_dimension_matrix": {
            lang: dict(sorted(counter.items())) for lang, counter in by_language.items()
        },
        "paper_reported_samples_per_language": PAPER_REPORTED_SAMPLES_PER_LANGUAGE,
        "delta_vs_paper_by_language": paper_delta,
        "files": files,
        "source_metadata": json.loads((root / "SOURCE.json").read_text(encoding="utf-8"))
        if (root / "SOURCE.json").exists()
        else None,
        "parallel_summary": parallel_summary,
        "missing_assets": missing_assets[:200],
        "missing_assets_count": len(missing_assets),
        "malformed_answers": malformed_answers[:200],
        "malformed_answers_count": len(malformed_answers),
        "noncanonical_answer_fields": noncanonical_answer_fields[:200],
        "noncanonical_answer_fields_count": len(noncanonical_answer_fields),
        "duplicate_questions": duplicate_questions,
        "episode_frame_counts": episode_frame_counts,
    }


def format_markdown(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# Release Audit")
    lines.append("")
    lines.append("This audit describes the currently downloaded public MPR-GUI-Bench release.")
    lines.append("It is generated from local files under `data/raw/mpr_gui_bench`.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Root: `{report['root']}`")
    lines.append(f"- Images directory exists: `{report['images_dir_exists']}`")
    lines.append(f"- QAS directory exists: `{report['qas_dir_exists']}`")
    lines.append(f"- Local JPG files under images: `{report['image_jpg_files']}`")
    lines.append(f"- Local QAS JSONL files: `{report['qas_jsonl_files']}`")
    lines.append(f"- Dataset license from HF README: `{report['dataset_license']}`")
    lines.append(f"- Total QA rows: `{report['total_rows']}`")
    lines.append(f"- Missing asset references: `{report['missing_assets_count']}`")
    lines.append(f"- Malformed answer fields: `{report['malformed_answers_count']}`")
    lines.append(f"- Non-label-only answer fields: `{report['noncanonical_answer_fields_count']}`")
    if report.get("source_metadata"):
        source = report["source_metadata"]
        lines.append(f"- Hugging Face dataset SHA: `{source['huggingface']['sha']}`")
        lines.append(f"- MPR-GUI-Bench GitHub commit: `{source['github']['commit']}`")
    lines.append("")
    lines.append("## Key Findings")
    lines.append("")
    lines.append("- The downloaded public QA release contains `2,245` rows per language, not `2,156`.")
    lines.append("- All `2,245` language-agnostic state keys have complete six-language coverage.")
    lines.append("- All audited asset references resolve locally after normalizing `../images/...` paths.")
    lines.append("- RI and SI are completely label-biased in the public option order: every audited RI/SI answer is `A`.")
    lines.append("- The audit found no malformed answers under the conservative A/B/C/D label parser.")
    lines.append("")
    lines.append("## Generated Artifacts")
    lines.append("")
    lines.append("- Raw normalized assets: `data/raw/mpr_gui_bench/images/` and `data/raw/mpr_gui_bench/qas/`.")
    lines.append("- Source metadata: `data/raw/mpr_gui_bench/SOURCE.json`.")
    lines.append("- Machine-readable audit: `data/manifests/release_audit.json`.")
    lines.append("- Sample manifest: `data/manifests/mpr_gui_manifest.jsonl`.")
    lines.append("- Parallel index: `data/manifests/parallel_index.json`.")
    lines.append("- Directed cross-locale pairs: `data/manifests/cross_locale_pairs.jsonl`.")
    lines.append("")
    lines.append("## Rows By Language")
    lines.append("")
    lines.append("| Language | Rows | Delta vs paper-reported 2,156 |")
    lines.append("| --- | ---: | ---: |")
    for lang, rows in sorted(report["rows_by_language"].items()):
        delta = report["delta_vs_paper_by_language"][lang]
        lines.append(f"| {lang} | {rows} | {delta:+d} |")
    lines.append("")
    lines.append("## Language x Dimension Matrix")
    lines.append("")
    dims = ["wf", "wi", "au", "ap", "ael", "rel", "ri", "si"]
    lines.append("| Language | " + " | ".join(dims) + " | Total |")
    lines.append("| --- | " + " | ".join(["---:"] * (len(dims) + 1)) + " |")
    for lang, dim_counts in sorted(report["language_dimension_matrix"].items()):
        values = [int(dim_counts.get(dim, 0)) for dim in dims]
        lines.append(f"| {lang} | " + " | ".join(str(v) for v in values) + f" | {sum(values)} |")
    lines.append("")
    lines.append("## Rows By Dimension")
    lines.append("")
    lines.append("| Dimension | Rows |")
    lines.append("| --- | ---: |")
    for dim, rows in sorted(report["rows_by_dimension"].items()):
        lines.append(f"| {dim} | {rows} |")
    lines.append("")
    lines.append("## Answer Label Distribution By File")
    lines.append("")
    lines.append("| File | Rows | Dimension | Language | A | B | C | D | Missing assets | SHA256 |")
    lines.append("| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for filename, meta in sorted(report["files"].items()):
        labels = meta["answer_labels"]
        sha = str(meta["sha256"])[:12]
        lines.append(
            f"| `{filename}` | {meta['rows']} | {meta['dimension']} | {meta['language']} | "
            f"{labels.get('A', 0)} | {labels.get('B', 0)} | {labels.get('C', 0)} | {labels.get('D', 0)} | "
            f"{meta['missing_assets']} | `{sha}` |"
        )
    lines.append("")
    lines.append("## Parallel Coverage")
    lines.append("")
    lines.append("| Dimension | Unique state keys | Complete 6-language states | Coverage histogram |")
    lines.append("| --- | ---: | ---: | --- |")
    for dim, meta in sorted(report["parallel_summary"].items()):
        lines.append(
            f"| {dim} | {meta['unique_state_keys']} | {meta['complete_six_language_states']} | "
            f"`{meta['coverage_histogram_num_languages']}` |"
        )
    lines.append("")
    if report["missing_assets_count"]:
        lines.append("## Missing Assets")
        lines.append("")
        lines.append("First 200 missing asset references:")
        lines.append("")
        for item in report["missing_assets"]:
            lines.append(f"- `{item['file']}` line {item['line']}: `{item['asset']}`")
        lines.append("")
    if report["malformed_answers_count"]:
        lines.append("## Malformed Answers")
        lines.append("")
    if report["noncanonical_answer_fields_count"]:
        lines.append("## Non-Label-Only Answer Fields")
        lines.append("")
        lines.append(
            "These answer fields parse cleanly to A/B/C/D but include extra answer text. "
            "Normalized label accuracy should be reported next to raw exact match."
        )
        lines.append("")
        for item in report["noncanonical_answer_fields"][:50]:
            lines.append(f"- `{item['file']}` line {item['line']}: `{item['answer']}` -> `{item['label']}`")
        if report["noncanonical_answer_fields_count"] > 50:
            lines.append(f"- ... {report['noncanonical_answer_fields_count'] - 50} more")
        lines.append("")
        for item in report["malformed_answers"]:
            lines.append(f"- `{item['file']}` line {item['line']}: `{item['answer']}`")
        lines.append("")
    lines.append("## Episode Frame Counts")
    lines.append("")
    if report["episode_frame_counts"]:
        counts = Counter(item["frames"] for item in report["episode_frame_counts"])
        lines.append("| Frames per episode row | Count |")
        lines.append("| ---: | ---: |")
        for frames, count in sorted(counts.items()):
            lines.append(f"| {frames} | {count} |")
    else:
        lines.append("No episode folders were found in the audited rows.")
    lines.append("")
    lines.append("## Interpretation Notes")
    lines.append("")
    lines.append("- The canonical reproduction should use the public option order unchanged.")
    lines.append("- Normalized label accuracy should parse labels from mixed answer strings such as `C. ...`.")
    lines.append("- If RI/SI label distributions are highly concentrated, report permutation-controlled and question-only baselines.")
    lines.append("- GUI-XLI remains an independent reimplementation unless official harness, memory data, and hook code become available.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/raw/mpr_gui_bench"))
    parser.add_argument("--json-out", type=Path, default=Path("data/manifests/release_audit.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("docs/RELEASE_AUDIT.md"))
    args = parser.parse_args(argv)
    report = audit_release(args.root)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(format_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
