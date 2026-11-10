#!/usr/bin/env bash
# Qwen3-VL-8B REL R_stem / R_opts (+ same-run O and R anchors) on ONE RTX 4090, batch 4.
# Usage (repo root, inside tmux, after steps 1-3 of followup_rel_4lang/RSTEM_ROPTS_RUNBOOK_KO.md):
#   bash followup_rel_4lang/run_rstem_ropts.sh smoke   # 3 items, 144 inferences, then gate
#   bash followup_rel_4lang/run_rstem_ropts.sh full    # 158 items, 7,584 inferences, gate, package
#   bash followup_rel_4lang/run_rstem_ropts.sh all     # smoke -> full -> package, stops at any failed gate
# Progress: cat $OUT/STATUS ; logs in $OUT/logs/. Rerunning the same command resumes.
set -Eeuo pipefail
STAGE="${1:?Give smoke, full or all}"
cd "$(dirname "$0")/.."
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.cache}"
export HF_HOME="${HF_HOME:-$XDG_CACHE_HOME/huggingface}"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
source .venv/bin/activate
source followup_rel_4lang/qwen3_4090_env.sh
MODEL_CONFIG=01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml
OUT=followup_rel_4lang/results/qwen3_rstem_ropts
mkdir -p "$OUT/logs"

status() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/STATUS"; }
trap 'status "FAILED at stage ${CURRENT:-?} (exit $?). See $OUT/logs/"' ERR

preflight() {
  CURRENT=preflight
  python - <<'PY'
import hashlib
from pathlib import Path
cfg = Path("01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml")
assert hashlib.sha256(cfg.read_bytes()).hexdigest() == \
    "2775bb6b981d35922c46545ef58af0ac8e8ded1a3615902c73ac141609adbc8b", "Model config differs from the 2026-11-07 run"
import json, sys
sys.path.insert(0, "01_code/src")
from mpr_crosslocale.inference.run_rel_followup import code_identity
old = json.loads(Path("followup_rel_4lang/rstem_ropts_inputs/run_contract_qwen3_rel_20261107.json").read_text())
diff = sorted(k for k, v in code_identity().items() if old["code_sha256"].get(k) != v)
assert not diff, f"Inference code differs from the 2026-11-07 run: {diff}"
import torch
name = torch.cuda.get_device_name(0)
assert torch.cuda.device_count() == 1 and "4090" in name, name
import transformers
want = old["software_versions"]
for pkg, have in (("torch", torch.__version__), ("transformers", transformers.__version__)):
    assert have == want[pkg], f"{pkg} {have} differs from 2026-11-07 run {want[pkg]}"
print("GPU", name, "| torch", torch.__version__)
PY
  test -s "$MODEL_SNAPSHOT/config.json"
  python followup_rel_4lang/data_bundle.py verify > "$OUT/logs/bundle_verify.log"
  python followup_rel_4lang/run_rel_mixed.py --model-config "$MODEL_CONFIG" \
    --output-dir "$OUT/dry_run" --dry-run > "$OUT/logs/dry_run.log"
  status "preflight passed"
}

run_smoke() {
  CURRENT=smoke
  status "smoke started"
  python followup_rel_4lang/run_rel_mixed.py --model-config "$MODEL_CONFIG" \
    --split main --max-items 3 --batch-size 4 --strict-batch-size --resume \
    --output-dir "$OUT/smoke" 2>&1 | tee -a "$OUT/logs/smoke.log"
  CURRENT=smoke_gate
  python followup_rel_4lang/check_rstem_gate.py smoke "$OUT/smoke" > "$OUT/logs/smoke_gate.log"
  status "smoke passed"
}

run_full() {
  CURRENT=full
  status "full started (7,584 inferences)"
  python followup_rel_4lang/run_rel_mixed.py --model-config "$MODEL_CONFIG" \
    --split main --batch-size 4 --strict-batch-size --resume \
    --output-dir "$OUT/full" 2>&1 | tee -a "$OUT/logs/full.log"
  CURRENT=complete_gate
  python followup_rel_4lang/check_rstem_gate.py complete "$OUT/full" > "$OUT/logs/complete_gate.log"
  status "full done"
}

package() {
  CURRENT=package
  git rev-parse HEAD > "$OUT/git_commit.txt" || true
  git status --short > "$OUT/git_status.txt" || true
  python -m pip freeze > "$OUT/requirements.freeze.txt"
  nvidia-smi > "$OUT/nvidia_smi.txt" || true
  ARCHIVE="${OUT%/}_$(date -u +%Y%m%d).tar.gz"
  tar -czf "$ARCHIVE" -C "$(dirname "$OUT")" "$(basename "$OUT")"
  status "ALL DONE. Download $ARCHIVE"
}

case "$STAGE" in
  smoke) preflight; run_smoke ;;
  full) preflight; run_full; package ;;
  all) preflight; run_smoke; run_full; package ;;
  *) echo "Unknown stage: $STAGE"; exit 1 ;;
esac
