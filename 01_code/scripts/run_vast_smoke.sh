#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${MANIFEST:-data/manifests/mpr_gui_manifest.jsonl}"
MODEL_CONFIG="${MODEL_CONFIG:-configs/models/qwen3_vl_4b_vast.yaml}"
MODEL_CONFIG_NAME="${MODEL_CONFIG##*/}"
MODEL_TAG="${MODEL_TAG:-${MODEL_CONFIG_NAME%.yaml}}"
OUTPUT="${OUTPUT:-results/raw/vast_smoke_${MODEL_TAG}.jsonl}"
FAILURES="${FAILURES:-results/raw/vast_smoke_${MODEL_TAG}_failures.jsonl}"
SUMMARY_JSON="${SUMMARY_JSON:-results/summaries/vast_smoke_${MODEL_TAG}.json}"
SUMMARY_CSV="${SUMMARY_CSV:-results/summaries/vast_smoke_${MODEL_TAG}.csv}"
PYTHON_BIN="${PYTHON_BIN:-python}"

test -s "${MANIFEST}" || {
  echo "Manifest not found. Run: bash scripts/prepare_vast_data.sh"
  exit 1
}

test -s "${MODEL_CONFIG}" || {
  echo "Model config not found: ${MODEL_CONFIG}"
  exit 1
}

"${PYTHON_BIN}" run_cross_locale.py \
  --manifest "${MANIFEST}" \
  --model-config "${MODEL_CONFIG}" \
  --language-pairs en:ja ja:en \
  --dimensions wf wi au ap ael rel \
  --sample-size 2 \
  --sample-unit semantic_items \
  --seed 42 \
  --device-map auto \
  --max-new-tokens 2 \
  --score-labels \
  --resume \
  --output "${OUTPUT}" \
  --failures-out "${FAILURES}"

"${PYTHON_BIN}" - "${OUTPUT}" <<'PY'
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
latest = {row["input_id"]: row for row in rows}
failed = [row for row in latest.values() if row.get("status") != "success"]

print("Latest evaluations:", len(latest))
print("Successful:", len(latest) - len(failed))
print("Failed:", len(failed))

if len(latest) != 4 or failed:
    raise SystemExit("Vast smoke test did not finish with four successful evaluations.")
PY

"${PYTHON_BIN}" -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input "${OUTPUT}" \
  --json-out "${SUMMARY_JSON}" \
  --csv-out "${SUMMARY_CSV}"
