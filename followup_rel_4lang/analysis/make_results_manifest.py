"""Record portable SHA-256 checksums for published REL GLMM outputs."""

import hashlib
import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
OUTPUTS = BASE / "results"
FOLDERS = ("analysis_ready", "glmm", "glmm_smoke")
EXPECTED_FILES = {"analysis_ready": 3, "glmm": 10, "glmm_smoke": 10}
TEXT_SUFFIXES = {".csv", ".json", ".txt"}


def canonical_bytes(path):
    payload = path.read_bytes()
    return payload.replace(b"\r\n", b"\n") if path.suffix in TEXT_SUFFIXES else payload


def main():
    report = json.loads((OUTPUTS / "analysis_ready/preparation_report.json").read_text(encoding="utf-8"))
    files = {}
    for folder in FOLDERS:
        paths = sorted(path for path in (OUTPUTS / folder).iterdir() if path.is_file())
        if len(paths) != EXPECTED_FILES[folder]:
            raise ValueError(f"Expected {EXPECTED_FILES[folder]} files in {folder}, found {len(paths)}")
        for path in paths:
            payload = canonical_bytes(path)
            relative = path.relative_to(BASE.parent).as_posix()
            files[relative] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
    manifest = {
        "schema": "rel-4lang-glmm-results-v1",
        "source_inference_commit": report["source_commit"],
        "conditions_sha256": report["conditions_sha256"],
        "glmm_rows_sha256": report["files"]["glmm_rows.csv"],
        "text_hash_policy": "SHA-256 after CRLF to LF normalization for .csv/.json/.txt; binary .rds is byte-exact",
        "files": files,
    }
    destination = Path(__file__).with_name("GLMM_RESULTS_MANIFEST.json")
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {destination} with {len(files)} result checksums")


if __name__ == "__main__":
    main()
