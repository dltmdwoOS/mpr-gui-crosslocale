#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${MANIFEST:-data/manifests/mpr_gui_manifest.jsonl}"
OUTPUT="${OUTPUT:-results/raw/vast_smoke.jsonl}"
FAILURES="${FAILURES:-results/raw/vast_smoke_failures.jsonl}"

test -s "${MANIFEST}" || {
  echo "Manifest not found. Run: bash scripts/prepare_vast_data.sh"
  exit 1
}

python run_cross_locale.py \
  --manifest "${MANIFEST}" \
  --model-config configs/models/qwen3_vl_4b_vast.yaml \
  --language-pairs en:ja ja:en \
  --dimensions wf wi au ap ael rel \
  --sample-size 2 \
  --sample-unit semantic_items \
  --seed 42 \
  --device-map auto \
  --attn-implementation sdpa \
  --max-new-tokens 2 \
  --score-labels \
  --resume \
  --output "${OUTPUT}" \
  --failures-out "${FAILURES}"

python - "${OUTPUT}" <<'PY'
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

python -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input "${OUTPUT}" \
  --json-out results/summaries/vast_smoke.json \
  --csv-out results/summaries/vast_smoke.csv
