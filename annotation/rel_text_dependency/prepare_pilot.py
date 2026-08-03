from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from huggingface_hub import hf_hub_download


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "01_code" / "src"))

from mpr_crosslocale.data.options import parse_question_options  # noqa: E402
from mpr_crosslocale.data.parallel_index import (  # noqa: E402
    canonical_state_key,
    normalize_asset_reference,
)


LANGUAGES = ("en", "zh", "fr", "ru", "ja", "th")
GITHUB_COMMIT = "e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba"
HF_REPO = "chenruihan/MPR-GUI-Bench"
HF_REVISION = "c1edb808d424a2fa7bc4a2e601d39b431b04acd5"
DEFAULT_SEED = 20260803
DEFAULT_SIZE = 48


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_url(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "mpr-rel-annotation/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def download_qas(data_dir: Path, force: bool = False) -> dict[str, Path]:
    result = {}
    for language in LANGUAGES:
        destination = data_dir / "qas" / f"rel_el_{language}.jsonl"
        if force or not destination.exists():
            url = (
                "https://raw.githubusercontent.com/chenruihan32/MPR-GUI-Bench/"
                f"{GITHUB_COMMIT}/qas/rel_el_{language}.jsonl"
            )
            download_url(url, destination)
        result[language] = destination
    return result


def load_items(qas_paths: dict[str, Path]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for language, path in qas_paths.items():
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                asset = normalize_asset_reference(row["image_path"])
                state_key = canonical_state_key(asset)
                parsed = parse_question_options(row["question"])
                if parsed.option_parse_status != "ok":
                    raise ValueError(f"Option parse failure: {path}:{line_no}")
                grouped[state_key][language] = {
                    "language": language,
                    "asset": asset,
                    "question_stem": parsed.question_stem,
                    "options": parsed.options,
                    "option_order": parsed.option_order,
                    "source_file": path.name,
                    "source_line": line_no,
                }

    items = []
    for state_key, locales in grouped.items():
        if set(locales) != set(LANGUAGES):
            raise ValueError(f"Incomplete locales for {state_key}: {sorted(locales)}")
        english_asset = str(locales["en"]["asset"])
        stratum = english_asset.split("/", 1)[0]
        items.append(
            {
                "parallel_id": f"rel::{state_key}",
                "state_key": state_key,
                "stratum": stratum,
                "locales": locales,
            }
        )
    if len(items) != 366:
        raise ValueError(f"Expected 366 REL items, found {len(items)}")
    return sorted(items, key=lambda item: str(item["parallel_id"]))


def stratified_sample(items: list[dict[str, object]], size: int, seed: int):
    strata: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        strata[str(item["stratum"])].append(item)
    rng = random.Random(seed)
    keys = sorted(strata)
    base_count, remainder = divmod(size, len(keys))
    selected = []
    allocation = {}
    for index, key in enumerate(keys):
        count = base_count + int(index < remainder)
        if count > len(strata[key]):
            raise ValueError(f"Requested {count} from stratum {key} with {len(strata[key])} items")
        allocation[key] = count
        selected.extend(rng.sample(strata[key], count))
    rng.shuffle(selected)
    for display_order, item in enumerate(selected, start=1):
        item["display_order"] = display_order
    return selected, allocation, {key: len(value) for key, value in strata.items()}


def quoted_gui_spans(text: str) -> list[tuple[int, int, str]]:
    """Find quoted GUI strings while ignoring apostrophes inside words."""
    spans: list[tuple[int, int, str]] = []
    occupied: set[int] = set()
    for match in re.finditer(r'"[^"\n]+"', text):
        spans.append((match.start(), match.end(), match.group(0)))
        occupied.update(range(match.start(), match.end()))

    delimiters = []
    for index, character in enumerate(text):
        if character != "'" or index in occupied:
            continue
        previous = text[index - 1] if index > 0 else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if previous.isalpha() and following.isalpha():
            continue
        delimiters.append(index)
    for start, end in zip(delimiters[0::2], delimiters[1::2]):
        spans.append((start, end + 1, text[start : end + 1]))
    return sorted(spans)


def protect_gui_tokens(text: str):
    spans = quoted_gui_spans(text)
    tokens = []
    protected = text
    for token_index, (start, end, original) in reversed(list(enumerate(spans))):
        token = f"XQZTOKEN{token_index}XQZ"
        tokens.append((token, original))
        protected = protected[:start] + token + protected[end:]
    return protected, list(reversed(tokens))


def restore_gui_tokens(text: str, tokens):
    for token, original in tokens:
        text = text.replace(token, original)
        text = text.replace(token.lower(), original)
    return text


def google_translate_helper(text: str) -> str:
    protected, tokens = protect_gui_tokens(text)
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "en",
            "tl": "ko",
            "dt": "t",
            "q": protected,
        }
    )
    url = "https://translate.googleapis.com/translate_a/single?" + query
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated = "".join(part[0] for part in payload[0] if part and part[0])
    return restore_gui_tokens(translated, tokens)


def build_translations(items: list[dict[str, object]], path: Path, force: bool = False):
    existing = {}
    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
    translations = existing.get("items", {})
    for index, item in enumerate(items, start=1):
        parallel_id = str(item["parallel_id"])
        if parallel_id in translations:
            continue
        english = item["locales"]["en"]
        fields = {"question_stem": english["question_stem"], **english["options"]}
        translated = {}
        for key, value in fields.items():
            for attempt in range(3):
                try:
                    translated[key] = google_translate_helper(str(value))
                    break
                except Exception:
                    if attempt == 2:
                        translated[key] = ""
                    time.sleep(1.5 * (attempt + 1))
            time.sleep(0.08)
        translations[parallel_id] = translated
        print(f"Translated {index}/{len(items)}: {parallel_id}", flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "translation_role": "Korean machine-generated annotation aid; English is authoritative.",
                    "translation_method": "Google Translate gtx endpoint with quoted GUI tokens protected",
                    "items": translations,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return translations


def download_images(items: list[dict[str, object]], data_dir: Path, workers: int):
    assets = sorted(
        {
            str(locale["asset"])
            for item in items
            for locale in item["locales"].values()
        }
    )
    destination_root = data_dir / "images"
    destination_root.mkdir(parents=True, exist_ok=True)

    def one(asset: str):
        destination = destination_root / Path(asset)
        if destination.exists() and destination.stat().st_size > 0:
            return asset, destination, False
        cached = Path(
            hf_hub_download(
                repo_id=HF_REPO,
                filename=asset,
                repo_type="dataset",
                revision=HF_REVISION,
            )
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, destination)
        return asset, destination, True

    downloaded = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(one, asset): asset for asset in assets}
        for completed, future in enumerate(as_completed(futures), start=1):
            asset, destination, was_downloaded = future.result()
            downloaded += int(was_downloaded)
            if destination.stat().st_size <= 0:
                raise ValueError(f"Empty image: {asset}")
            print(f"Image {completed}/{len(assets)}: {asset}", flush=True)
    return {"assets": len(assets), "newly_downloaded": downloaded}


def write_manifest(items, translations, path: Path):
    manifest_items = []
    for item in sorted(items, key=lambda row: row["display_order"]):
        parallel_id = str(item["parallel_id"])
        record = {
            "parallel_id": parallel_id,
            "state_key": item["state_key"],
            "stratum": item["stratum"],
            "display_order": item["display_order"],
            "ko_helper": translations.get(parallel_id, {}),
            "locales": item["locales"],
        }
        # Gold answers stay out of the manifest. The UI joins them from the
        # locked QAS files at runtime so the sampled manifest remains stable.
        manifest_items.append(record)
    payload = {
        "schema_version": "1.0",
        "guideline_version": "pilot-v1",
        "selection": {
            "dimension": "rel",
            "sample_size": len(items),
            "blind_to_model_outputs": True,
            "gold_in_manifest": False,
            "gold_in_ui": True,
        },
        "source": {
            "github_commit": GITHUB_COMMIT,
            "hf_repo": HF_REPO,
            "hf_revision": HF_REVISION,
        },
        "items": manifest_items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def translation_token_mismatches(items, translations):
    mismatches = []
    for item in items:
        parallel_id = str(item["parallel_id"])
        english = item["locales"]["en"]
        translated = translations.get(parallel_id, {})
        fields = {"question_stem": english["question_stem"], **english["options"]}
        for field, source in fields.items():
            target = translated.get(field, "")
            for _, _, token in quoted_gui_spans(str(source)):
                if token not in target:
                    mismatches.append(
                        {
                            "parallel_id": parallel_id,
                            "field": field,
                            "missing_token": token,
                            "translation": target,
                        }
                    )
    return mismatches


def main():
    parser = argparse.ArgumentParser(description="Prepare the blind REL text-dependency pilot.")
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--force-qas", action="store_true")
    parser.add_argument("--force-translation", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)

    qas_paths = download_qas(args.data_dir, force=args.force_qas)
    all_items = load_items(qas_paths)
    selected, allocation, population = stratified_sample(
        all_items, args.sample_size, args.seed
    )
    translation_path = args.data_dir / "translations_ko.json"
    translations = {}
    if not args.skip_translation:
        translations = build_translations(
            selected, translation_path, force=args.force_translation
        )
    selected_assets = {
        str(locale["asset"])
        for item in selected
        for locale in item["locales"].values()
    }
    existing_images = sum(
        (args.data_dir / "images" / asset).is_file() for asset in selected_assets
    )
    image_report = {
        "assets": len(selected_assets),
        "existing": existing_images,
        "newly_downloaded": 0,
    }
    if not args.skip_images:
        image_report = download_images(selected, args.data_dir, args.workers)
        image_report["existing"] = len(selected_assets)

    manifest_path = args.data_dir / "pilot_manifest.json"
    write_manifest(selected, translations, manifest_path)
    report = {
        "sample_size": len(selected),
        "seed": args.seed,
        "population_by_stratum": population,
        "sample_by_stratum": allocation,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "qas_sha256": {lang: sha256(path) for lang, path in qas_paths.items()},
        "translation_items": len(translations),
        "translation_quoted_token_mismatches": translation_token_mismatches(
            selected, translations
        ),
        "images": image_report,
        "gold_fields_in_manifest": False,
    }
    (args.data_dir / "preparation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
