"""Summarize and archive the completed RTX 4090 diagnostics without GPU inference."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def summarize(base: Path) -> dict:
    core_validation = read(base / "core_manifest_validation.json")
    if not core_validation["ok"] or not read(base / "rel_data_audit.json")["structural_checks_passed"]:
        raise ValueError("Dataset validation did not pass")
    suites = {}
    for name in ("controls_2mp_channels_last", "controls_1mp_channels_last",
                 "pilot_2mp_channels_last", "pilot_1mp_channels_last"):
        suites[name] = read(base / name / "summary.json")
        if not suites[name]["complete"]:
            raise ValueError(f"Incomplete suite: {name}")
        contract = read(base / name / "run_contract.json")
        if contract["runner_sha256"] != sha((HERE / "run_qwen3_grounding.py").read_bytes()):
            raise ValueError("Runner changed since the experiment; archive its original source first")
        for filename, expected in contract["implementation_sha256"].items():
            source = HERE / filename
            if not source.exists():
                source = REPO / "01_code/src/mpr_crosslocale/models" / filename
            if sha(source.read_bytes()) != expected:
                raise ValueError(f"Implementation changed since the experiment: {filename}")
    high = {r["trial_id"]: r for r in rows(base / "pilot_2mp_channels_last/predictions.jsonl")}
    low = {r["trial_id"]: r for r in rows(base / "pilot_1mp_channels_last/predictions.jsonl")}
    assert set(high) == set(low) and len(high) == 144
    transitions = {}
    for condition in ("O", "R", "C"):
        selected = [key for key, row in high.items() if row["condition"] == condition]
        transitions[condition] = {
            "lost_at_1mp": sum(high[k]["point_in_gt_box"] and not low[k]["point_in_gt_box"] for k in selected),
            "gained_at_1mp": sum(not high[k]["point_in_gt_box"] and low[k]["point_in_gt_box"] for k in selected),
        }
    old = rows(REPO / "followup_rel_4lang/results/grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl")
    legacy = {"count": len(old),
              "raw_equal": sum(r["raw_output"] == high[r["trial_id"]]["raw_output"] for r in old),
              "hit_equal": sum(r["point_in_gt_box"] == high[r["trial_id"]]["point_in_gt_box"] for r in old)}
    matrix = {}
    for path in sorted(base.glob("rtx4090_booking10_*.json")):
        record = read(path)
        if "generate_s" not in record:
            continue
        matrix[path.name] = {key: record[key] for key in (
            "max_pixels", "batch_size", "generate_s", "vision_forward_s", "language_prefill_s",
            "peak_allocated_gib", "peak_reserved_gib")}
        matrix[path.name]["patch_embed_memory_format"] = record.get("patch_embed_memory_format", "native")
    cross = rows(base / "6x6_smoke.jsonl")
    assert len(cross) == 36 and all(r["status"] == "success" for r in cross)
    rel = read(base / "rel_qwen3_smoke/summary.json")
    if rel["statuses"].get("pending", 0) or rel["statuses"].get("failed", 0):
        raise ValueError("REL smoke incomplete")
    baseline = read(base / "rtx4090_booking10_2mp_b3.json")
    changed = read(base / "rtx4090_booking10_2mp_b3_channels_last.json")
    return {
        "schema": "qwen3-rtx4090-study-summary-v1", "date": "2026-11-05",
        "native_to_channels_last_speedup_one_batch": baseline["generate_s"] / changed["generate_s"],
        "same_booking10_coordinates": [r["raw_output"] for r in baseline["results"]]
        == [r["raw_output"] for r in changed["results"]],
        "runtime_matrix": matrix, "suites": suites, "resolution_transitions": transitions,
        "legacy_b200_12_response_comparison": legacy,
        "cross_locale_smoke": {"responses": len(cross), "success": len(cross),
                               "parsed": sum(r.get("parse_success", False) for r in cross),
                               "runtime_s_total": sum(r["runtime_ms"] for r in cross) / 1000},
        "rel_smoke": rel, "execution_plan": read(base / "execution_plan.json"),
        "core_data_validation": core_validation,
        "main_descriptors_finalized": False,
        "interpretation": "Exploratory pilot on 12 items. Layout policy changes BF16 numerical outputs; keep separate contracts. Main inference was not run.",
    }


def verify(directory: Path) -> int:
    manifest = read(directory / "artifact_manifest.json")
    for entry in manifest["files"]:
        data = (directory / entry["path"]).read_bytes()
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {entry['path']}")
        if entry["path"].endswith(".gz") and sha(gzip.decompress(data)) != entry["uncompressed_sha256"]:
            raise ValueError("Uncompressed artifact checksum mismatch")
    return len(manifest["files"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=REPO / "followup_rel_4lang/results/runtime_probe")
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps({"verified_files": verify(args.archive_dir)}))
        return
    summary = summarize(args.results_dir)
    if args.archive_dir.exists():
        parser.error("Use a fresh archive directory")
    args.archive_dir.mkdir(parents=True)
    (args.archive_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    wanted = (list(args.results_dir.glob("rtx4090_*.json")) + [args.results_dir / name for name in (
        "environment.json", "requirements.freeze.txt", "conv3d_dispatch.json", "core_data_audit.json",
        "rel_data_audit.json", "rel_images_prepared.json", "execution_plan.json", "core_manifest_validation.json",
        "qwen3_rel_adapter_smoke.json", "6x6_smoke.jsonl", "6x6_smoke.jsonl.contract.json",
        "main_descriptors_draft_v2.json")])
    for path in wanted:
        shutil.copyfile(path, args.archive_dir / path.name)
    for name in ("controls_2mp_channels_last", "controls_1mp_channels_last",
                 "pilot_2mp_channels_last", "pilot_1mp_channels_last", "rel_qwen3_smoke"):
        destination = args.archive_dir / name
        destination.mkdir()
        for filename in ("summary.json", "run_contract.json"):
            shutil.copyfile(args.results_dir / name / filename, destination / filename)
        for filename in ("predictions.jsonl", "batches.jsonl", "results.jsonl"):
            source = args.results_dir / name / filename
            if source.exists():
                (destination / (filename + ".gz")).write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    snapshots = args.archive_dir / "source_snapshots"
    snapshots.mkdir()
    for path in (HERE / "run_qwen3_grounding.py", HERE / "benchmark_qwen3_runtime.py",
                 HERE / "run_qwen3_prompt_pilot.py", HERE / "point_format.py",
                 REPO / "01_code/src/mpr_crosslocale/models/qwen3_memory.py"):
        shutil.copyfile(path, snapshots / path.name)
    entries = []
    for path in sorted(args.archive_dir.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        entry = {"path": path.relative_to(args.archive_dir).as_posix(), "bytes": len(data), "sha256": sha(data)}
        if path.suffix == ".gz":
            raw = gzip.decompress(data)
            entry.update(uncompressed_sha256=sha(raw), uncompressed_lines=len(raw.splitlines()))
        entries.append(entry)
    (args.archive_dir / "artifact_manifest.json").write_text(json.dumps({"schema": "qwen3-rtx4090-artifacts-v1", "files": entries}, indent=2) + "\n")
    print(json.dumps({"verified_files": verify(args.archive_dir), "archive": str(args.archive_dir)}))


if __name__ == "__main__":
    main()
