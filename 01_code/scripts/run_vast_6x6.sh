#!/usr/bin/env bash
set -euo pipefail

SAMPLE_SIZE="${SAMPLE_SIZE:-}"
MANIFEST="${MANIFEST:-data/manifests/mpr_gui_manifest.jsonl}"
MODEL_CONFIG="${MODEL_CONFIG:-configs/models/qwen2_5_vl_7b.yaml}"
MODEL_CONFIG_NAME="${MODEL_CONFIG##*/}"
MODEL_TAG="${MODEL_TAG:-${MODEL_CONFIG_NAME%.yaml}}"
OUTPUT="${OUTPUT:-results/raw/vast_6x6_${MODEL_TAG}.jsonl}"
FAILURES="${FAILURES:-results/raw/vast_6x6_${MODEL_TAG}_failures.jsonl}"
SUMMARY_JSON="${SUMMARY_JSON:-results/summaries/vast_6x6_${MODEL_TAG}.json}"
SUMMARY_CSV="${SUMMARY_CSV:-results/summaries/vast_6x6_${MODEL_TAG}.csv}"
PYTHON_BIN="${PYTHON_BIN:-python}"

test -n "${SAMPLE_SIZE}" || {
  echo "Set SAMPLE_SIZE explicitly. Example: SAMPLE_SIZE=1 bash scripts/run_vast_6x6.sh"
  exit 1
}

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
  --dimensions wf wi au ap ael rel \
  --sample-size "${SAMPLE_SIZE}" \
  --sample-unit semantic_items \
  --seed 42 \
  --device-map auto \
  --max-new-tokens 2 \
  --score-labels \
  --resume \
  --output "${OUTPUT}" \
  --failures-out "${FAILURES}"

"${PYTHON_BIN}" -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input "${OUTPUT}" \
  --json-out "${SUMMARY_JSON}" \
  --csv-out "${SUMMARY_CSV}"
