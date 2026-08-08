from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory

from annotation_store import AnnotationStore


HERE = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = HERE / "data"
DEFAULT_OUTPUT_DIR = HERE / "outputs"
ANNOTATOR_RE = re.compile(r"^[A-Za-z0-9가-힣_.-]{1,80}$")


def canonical_text_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def normalize_asset(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    normalized = normalized.removeprefix("./").removeprefix("images/")
    return normalized


def load_gold_by_asset(qas_dir: Path) -> dict[str, str]:
    gold_by_asset: dict[str, str] = {}
    for language in ("en", "zh", "fr", "ru", "ja", "th"):
        path = qas_dir / f"rel_el_{language}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"REL QAS not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                answer = str(row.get("answer", "")).strip().upper()
                if answer not in {"A", "B", "C", "D"}:
                    raise ValueError(f"Invalid gold answer in {path}: {answer}")
                gold_by_asset[normalize_asset(str(row["image_path"]))] = answer
    return gold_by_asset


def create_app(data_dir: Path = DEFAULT_DATA_DIR, output_dir: Path = DEFAULT_OUTPUT_DIR):
    manifest_path = data_dir / "pilot_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Pilot manifest not found: {manifest_path}. Run prepare_pilot.py first."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = sorted(manifest["items"], key=lambda item: item["display_order"])
    item_by_id = {item["parallel_id"]: item for item in items}
    manifest_hash = canonical_text_sha256(manifest_path)
    guideline_version = manifest.get("guideline_version", "pilot-v1")
    gold_by_asset = load_gold_by_asset(data_dir / "qas")
    store = AnnotationStore(output_dir / "rel_text_dependency.sqlite3")
    store.reconcile_manifest(
        items,
        guideline_version=guideline_version,
        manifest_sha256=manifest_hash,
    )

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        JSON_AS_ASCII=False,
        MAX_CONTENT_LENGTH=64 * 1024,
        DATA_DIR=data_dir,
        OUTPUT_DIR=output_dir,
    )

    def valid_annotator(value: str) -> str:
        value = (value or "").strip()
        if not ANNOTATOR_RE.fullmatch(value):
            abort(400, "Annotator ID: 한글·영문·숫자·._-만 사용할 수 있습니다.")
        return value

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            total_items=len(items),
            guideline_version=guideline_version,
            manifest_sha256=manifest_hash,
        )

    @app.get("/api/items")
    def api_items():
        annotator = valid_annotator(request.args.get("annotator", ""))
        annotations = {
            row["parallel_id"]: row for row in store.all_for(annotator)
        }
        summaries = []
        for item in items:
            annotation = annotations.get(item["parallel_id"])
            summaries.append(
                {
                    "parallel_id": item["parallel_id"],
                    "display_order": item["display_order"],
                    "stratum": item["stratum"],
                    "label": annotation["label"] if annotation else None,
                    "review_flag": bool(annotation["review_flag"]) if annotation else False,
                }
            )
        return jsonify(
            {
                "items": summaries,
                "progress": store.progress(annotator, len(items)),
                "guideline_version": guideline_version,
                "manifest_sha256": manifest_hash,
            }
        )

    @app.get("/api/item/<int:display_order>")
    def api_item(display_order: int):
        annotator = valid_annotator(request.args.get("annotator", ""))
        if not 1 <= display_order <= len(items):
            abort(404)
        item = items[display_order - 1]
        annotation = store.get(annotator, item["parallel_id"])
        public_item = json.loads(json.dumps(item))
        for locale in public_item["locales"].values():
            locale["image_url"] = "/images/" + locale["asset"]
            locale["correct_answer"] = gold_by_asset[locale["asset"]]
            locale.pop("source_file", None)
            locale.pop("source_line", None)
        return jsonify(
            {
                "item": public_item,
                "annotation": annotation,
                "total_items": len(items),
            }
        )

    @app.post("/api/annotate")
    def api_annotate():
        payload = request.get_json(force=True)
        annotator = valid_annotator(str(payload.get("annotator_id", "")))
        parallel_id = str(payload.get("parallel_id", ""))
        if parallel_id not in item_by_id:
            abort(400, "Unknown parallel_id")
        item = item_by_id[parallel_id]
        try:
            saved = store.upsert(
                annotator_id=annotator,
                parallel_id=parallel_id,
                display_order=int(item["display_order"]),
                label=payload.get("label"),
                review_flag=bool(payload.get("review_flag", False)),
                note=str(payload.get("note", "")),
                current_locale=str(payload.get("current_locale", "en")),
                annotation_seconds=float(payload.get("annotation_seconds", 0)),
                guideline_version=guideline_version,
                manifest_sha256=manifest_hash,
            )
        except ValueError as error:
            abort(400, str(error))
        return jsonify(
            {
                "saved": saved,
                "progress": store.progress(annotator, len(items)),
            }
        )

    @app.get("/api/export")
    def api_export():
        annotator = valid_annotator(request.args.get("annotator", ""))
        csv_text = store.export_csv(annotator)
        safe_name = re.sub(r"[^A-Za-z0-9가-힣_.-]", "_", annotator)
        return Response(
            "\ufeff" + csv_text,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="rel_pilot_{safe_name}.csv"'
            },
        )

    @app.get("/images/<path:asset>")
    def images(asset: str):
        normalized = Path(asset)
        if normalized.is_absolute() or ".." in normalized.parts:
            abort(404)
        return send_from_directory(data_dir / "images", asset)

    @app.get("/api/health")
    def health():
        image_count = sum(
            1
            for item in items
            for locale in item["locales"].values()
            if (data_dir / "images" / locale["asset"]).is_file()
        )
        return jsonify(
            {
                "status": "ok" if image_count == len(items) * 6 else "incomplete",
                "items": len(items),
                "images": image_count,
                "expected_images": len(items) * 6,
                "manifest_sha256": manifest_hash,
                "gold_in_manifest": False,
                "gold_in_ui": True,
            }
        )

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the local REL annotation UI.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--annotator", default="")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"} and os.environ.get(
        "ALLOW_REMOTE_ANNOTATION"
    ) != "1":
        raise SystemExit(
            "Remote binding is disabled by default. Set ALLOW_REMOTE_ANNOTATION=1 explicitly."
        )
    app = create_app(args.data_dir, args.output_dir)
    if args.open_browser:
        suffix = ""
        if args.annotator:
            suffix = "?annotator=" + urllib.parse.quote(args.annotator)
        url = f"http://{args.host}:{args.port}/{suffix}"
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
