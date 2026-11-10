#!/usr/bin/env bash
# InternVL3.5-8B: 6x6, REL O/R/C/F and grounding O/R/C/F on ONE RTX 4090, batch 1.
# Usage (repo root, inside tmux, after runbook steps 1-2):
#   bash followup_rel_4lang/run_full_internvl35.sh all     # unattended: preflight -> smoke -> full -> package
#   bash followup_rel_4lang/run_full_internvl35.sh smoke   # small checks only
#   bash followup_rel_4lang/run_full_internvl35.sh full    # full GPU inference only
# Progress: cat $OUT/STATUS ; logs in $OUT/logs/. Rerunning the same command resumes.
set -Eeuo pipefail
STAGE="${1:?Give all, smoke or full}"
cd "$(dirname "$0")/.."
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
source .venv/bin/activate
source followup_rel_4lang/internvl35_4090_env.sh
mkdir -p "$OUT/logs"
MANIFEST=01_code/data/manifests/mpr_gui_manifest.jsonl

status() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/STATUS"; }
trap 'status "FAILED at stage ${CURRENT:-?} (exit $?). See $OUT/logs/"' ERR

run_preflight() {
  CURRENT=preflight
  if [ ! -s "$OUT/preflight.json" ]; then
    status "preflight started"
    python followup_rel_4lang/check_internvl_preflight.py --manifest "$MANIFEST" \
      --model-config "$MODEL_CONFIG" --output "$OUT/preflight.json" 2>&1 | tee "$OUT/logs/preflight.log"
  fi
  python - <<'PY'
import hashlib, json, os
from pathlib import Path
r = json.loads(Path(os.environ["OUT"], "preflight.json").read_text())
assert r["status"] == "passed", "Preflight did not pass"
assert r["config_sha256"] == hashlib.sha256(Path(os.environ["MODEL_CONFIG"]).read_bytes()).hexdigest(), "Config changed since preflight"
assert r["manifest_sha256"] == hashlib.sha256(Path("01_code/data/manifests/mpr_gui_manifest.jsonl").read_bytes()).hexdigest(), "Manifest changed since preflight"
assert "4090" in r["gpu"]
print("Preflight record OK:", r["model_id"], r["revision"], r["measured_runtime"])
PY
  python followup_rel_4lang/check_internvl_gates.py eta "$OUT" > "$OUT/logs/eta.log"
  status "preflight passed; ETA $(python -c "import json;print(json.load(open('$OUT/gate_eta.json'))['estimated_hours'])") hours"
}

run_smoke() {
  CURRENT=smoke
  status "smoke started"
  python 01_code/run_cross_locale.py \
    --manifest "$MANIFEST" --repo-root 01_code \
    --model-config "$MODEL_CONFIG" --dimensions wf wi au ap ael rel \
    --sample-size 6 --sample-unit semantic_items --seed 42 --batch-size 1 \
    --score-labels --system-prompt-mode english_fixed --device-map cuda:0 --resume \
    --output "$OUT/smoke_6x6.jsonl" --failures-out "$OUT/smoke_6x6_failures.jsonl" \
    2>&1 | tee -a "$OUT/logs/smoke_6x6.log"
  python followup_rel_4lang/run_inference.py \
    --model-config "$MODEL_CONFIG" --batch-size 1 --max-items 2 --resume \
    --output-dir "$OUT/smoke_rel" 2>&1 | tee -a "$OUT/logs/smoke_rel.log"
  python followup_rel_4lang/grounding_eval/run_internvl_grounding.py \
    --model-config "$MODEL_CONFIG" --suite pilot --output-dir "$OUT/pilot_orcf" \
    2>&1 | tee -a "$OUT/logs/pilot_orcf.log"
  CURRENT=smoke_gate
  python followup_rel_4lang/check_internvl_gates.py smoke "$OUT" > "$OUT/logs/smoke_gate.log"
  status "smoke passed"
}

run_full() {
  CURRENT=full_6x6
  status "full 6x6 started"
  python 01_code/run_cross_locale.py \
    --manifest "$MANIFEST" --repo-root 01_code \
    --model-config "$MODEL_CONFIG" --dimensions wf wi au ap ael rel \
    --sample-unit semantic_items --seed 42 --batch-size 1 \
    --score-labels --system-prompt-mode english_fixed --device-map cuda:0 --resume \
    --output "$OUT/full_6x6.jsonl" --failures-out "$OUT/full_6x6_failures.jsonl" \
    --sample-manifest-out "$OUT/full_6x6_plan.json" \
    2>&1 | tee -a "$OUT/logs/full_6x6.log"
  python -m mpr_crosslocale.analysis.summarize_cross_locale \
    --input "$OUT/full_6x6.jsonl" \
    --json-out "$OUT/full_6x6_summary.json" --csv-out "$OUT/full_6x6_summary.csv"
  status "full 6x6 done"
  CURRENT=full_rel
  python followup_rel_4lang/run_inference.py \
    --model-config "$MODEL_CONFIG" --batch-size 1 --resume \
    --output-dir "$OUT/full_rel" 2>&1 | tee -a "$OUT/logs/full_rel.log"
  status "full REL done"
  CURRENT=full_grounding
  python followup_rel_4lang/grounding_eval/run_internvl_grounding.py \
    --model-config "$MODEL_CONFIG" --suite main --descriptors "$DESCRIPTORS" \
    --output-dir "$OUT/grounding_main_orcf" 2>&1 | tee -a "$OUT/logs/grounding_main_orcf.log"
  status "full grounding done"
}

package() {
  CURRENT=package
  python followup_rel_4lang/check_internvl_gates.py complete "$OUT" > "$OUT/logs/complete_gate.log"
  git rev-parse HEAD > "$OUT/git_commit.txt"
  git status --short > "$OUT/git_status.txt"
  python -m pip freeze > "$OUT/requirements.freeze.txt"
  tar -czf "${OUT%/}_$(date -u +%Y%m%d).tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
  status "ALL DONE. Download ${OUT%/}_$(date -u +%Y%m%d).tar.gz"
}

case "$STAGE" in
  all) run_preflight; run_smoke; run_full; package ;;
  smoke) run_preflight; run_smoke ;;
  full) run_preflight; run_full; package ;;
  *) echo "Unknown stage: $STAGE"; exit 1 ;;
esac
