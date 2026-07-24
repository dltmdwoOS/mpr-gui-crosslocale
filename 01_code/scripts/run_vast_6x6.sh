#!/usr/bin/env bash
set -euo pipefail

SAMPLE_SIZE="${SAMPLE_SIZE:-}"
MANIFEST="${MANIFEST:-data/manifests/mpr_gui_manifest.jsonl}"
OUTPUT="${OUTPUT:-results/raw/vast_6x6_qwen3vl4b.jsonl}"
FAILURES="${FAILURES:-results/raw/vast_6x6_qwen3vl4b_failures.jsonl}"

test -n "${SAMPLE_SIZE}" || {
  echo "Set SAMPLE_SIZE explicitly. Example: SAMPLE_SIZE=1 bash scripts/run_vast_6x6.sh"
  exit 1
}

test -s "${MANIFEST}" || {
  echo "Manifest not found. Run: bash scripts/prepare_vast_data.sh"
  exit 1
}

python run_cross_locale.py \
  --manifest "${MANIFEST}" \
  --model-config configs/models/qwen3_vl_4b_vast.yaml \
  --dimensions wf wi au ap ael rel \
  --sample-size "${SAMPLE_SIZE}" \
  --sample-unit semantic_items \
  --seed 42 \
  --device-map auto \
  --attn-implementation sdpa \
  --max-new-tokens 2 \
  --score-labels \
  --resume \
  --output "${OUTPUT}" \
  --failures-out "${FAILURES}"

python -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input "${OUTPUT}" \
  --json-out results/summaries/vast_6x6_qwen3vl4b.json \
  --csv-out results/summaries/vast_6x6_qwen3vl4b.csv
