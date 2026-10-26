"""Local, output-blind bounding-box annotation UI for the REL grounding pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LANGUAGES = ("en", "zh", "th", "ru")
STATUSES = {"valid", "ambiguous", "multiple_matches", "absent", "unpointable", "screenshot_error"}
EQUIVALENCE = {"yes", "no", "uncertain"}
ROLES = {"button", "label", "control", "section", "row", "icon", "other"}
ANNOTATOR_RE = re.compile(r"^[A-Za-z0-9가-힣_.-]{1,80}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_box(value: object, width: int, height: int, name: str) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) for v in value
    ):
        raise ValueError(f"{name} must be [x1,y1,x2,y2] numbers")
    x1, y1, x2, y2 = (float(v) for v in value)
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f"{name} is outside the original image or has zero area")
    return [x1, y1, x2, y2]


def validate_annotation(payload: dict, locale: dict) -> dict:
    status = payload.get("status")
    if status not in STATUSES:
        raise ValueError("Select a target status")
    reference_equivalence = payload.get("reference_equivalence")
    options_equivalence = payload.get("options_equivalence")
    if reference_equivalence not in EQUIVALENCE or options_equivalence not in EQUIVALENCE:
        raise ValueError("Select reference and option equivalence")
    phrase = str(payload.get("anchor_phrase", "")).strip()
    stem = locale["question_stem"]
    anchor = locale["stem_span"]["text"]
    if not phrase or phrase not in stem or phrase.count(anchor) != 1:
        raise ValueError("Anchor phrase must be an exact stem substring containing the highlighted span once")
    width, height = int(locale["width"]), int(locale["height"])
    box = validate_box(payload.get("bbox"), width, height, "bbox")
    label_box = validate_box(payload.get("label_bbox"), width, height, "label_bbox")
    role = payload.get("element_role")
    if status == "valid":
        if box is None or role not in ROLES:
            raise ValueError("Valid targets require a primary bbox and element role")
    elif box is not None or label_box is not None:
        raise ValueError("Invalid/ambiguous targets must not have boxes")
    elif role is not None:
        raise ValueError("Invalid/ambiguous targets must not have an element role")
    note = str(payload.get("note", "")).strip()
    if len(note) > 2000:
        raise ValueError("Note is too long")
    if (status != "valid" or reference_equivalence != "yes" or options_equivalence != "yes") and not note:
        raise ValueError("Explain any invalid or uncertain status in the note")
    return {
        "status": status,
        "reference_equivalence": reference_equivalence,
        "options_equivalence": options_equivalence,
        "anchor_phrase": phrase,
        "element_role": role if status == "valid" else None,
        "bbox": box,
        "label_bbox": label_box,
        "note": note,
    }


def create_app(
    manifest_path: Path = HERE / "data/pilot_manifest.json",
    output_dir: Path = HERE / "outputs",
    annotator_id: str = "annotator_1",
    repo_root: Path = REPO,
) -> Flask:
    if not ANNOTATOR_RE.fullmatch(annotator_id):
        raise ValueError("Annotator ID must contain 1–80 letters, numbers, ._- only")
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "rel-grounding-pilot-v1":
        raise ValueError("Unknown pilot manifest schema")
    manifest_hash = digest(manifest_path)
    items = {item["parallel_id"]: item for item in manifest["items"]}
    if len(items) != len(manifest["items"]):
        raise ValueError("Duplicate pilot item ID")
    image_by_key = {}
    root = (repo_root / "followup_rel_4lang").resolve()
    for pid, item in items.items():
        if set(item["locales"]) != set(LANGUAGES):
            raise ValueError(f"Incomplete locales for {pid}")
        for language, locale in item["locales"].items():
            path = (root / locale["image_path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Missing or unsafe image: {locale['image_path']}")
            if digest(path) != locale["image_sha256"]:
                raise ValueError(f"Image changed since pilot packet was generated: {locale['image_path']}")
            image_by_key[pid, language] = path
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{annotator_id}.json"
    lock = threading.Lock()

    def load_state() -> dict:
        if output.exists():
            state = json.loads(output.read_text(encoding="utf-8"))
            if state.get("manifest_sha256") != manifest_hash or state.get("annotator_id") != annotator_id:
                raise ValueError("Existing annotations belong to a different manifest or annotator")
            return state
        return {"schema": "rel-grounding-annotations-v1", "manifest_sha256": manifest_hash,
                "annotator_id": annotator_id, "annotations": {}}

    def save_state(state: dict) -> None:
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)

    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

    @app.get("/")
    def index():
        return send_file(HERE / "static/index.html")

    @app.get("/api/state")
    def state():
        with lock:
            saved = load_state()
        return jsonify({"manifest": manifest, "annotations": saved["annotations"],
                        "annotator_id": annotator_id, "manifest_sha256": manifest_hash})

    @app.get("/api/image")
    def image():
        path = image_by_key.get((request.args.get("pid"), request.args.get("lang")))
        if path is None:
            abort(404)
        return send_file(path)

    @app.post("/api/annotation")
    def annotate():
        payload = request.get_json(force=True)
        pid, language = payload.get("parallel_id"), payload.get("language")
        if pid not in items or language not in LANGUAGES:
            abort(400, "Unknown item or locale")
        try:
            annotation = validate_annotation(payload, items[pid]["locales"][language])
            with lock:
                saved = load_state()
                saved["annotations"].setdefault(pid, {})[language] = {
                    **annotation,
                    "image_sha256": items[pid]["locales"][language]["image_sha256"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                save_state(saved)
        except ValueError as exc:
            abort(400, str(exc))
        return jsonify({"saved": True, "annotation": saved["annotations"][pid][language]})

    @app.get("/api/export")
    def export():
        with lock:
            saved = load_state()
        return Response(json.dumps(saved, ensure_ascii=False, indent=2) + "\n",
                        mimetype="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{annotator_id}.json"'})

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotator", required=True)
    parser.add_argument("--manifest", type=Path, default=HERE / "data/pilot_manifest.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "outputs")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    app = create_app(args.manifest, args.output_dir, args.annotator)
    if args.open_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)


if __name__ == "__main__":
    main()
