#!/usr/bin/env bash
# InternVL3.5-8B REL R_stem / R_opts (+ same-run O and R anchors) on ONE RTX 4090, batch 1.
# Code: commit 666440 + rstem_internvl_patches/0001-0005 (= code of the 2026-11-09 InternVL3.5 run).
# Usage (repo root, inside tmux, after steps 1-3 of followup_rel_4lang/RSTEM_ROPTS_INTERNVL_RUNBOOK_KO.md):
#   bash followup_rel_4lang/run_rstem_ropts_internvl.sh smoke   # 3 items, 144 inferences, then gate
#   bash followup_rel_4lang/run_rstem_ropts_internvl.sh full    # 158 items, 7,584 inferences, gate, package
#   bash followup_rel_4lang/run_rstem_ropts_internvl.sh all     # smoke -> full -> package, stops at any failed gate
# Progress: cat $OUT/STATUS ; logs in $OUT/logs/. Rerunning the same command resumes.
set -Eeuo pipefail
STAGE="${1:?Give smoke, full or all}"
cd "$(dirname "$0")/.."
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
source .venv/bin/activate
source followup_rel_4lang/internvl35_4090_env.sh
MODEL_CONFIG=01_code/configs/models/internvl3_5_8b_4090.yaml
OUT=followup_rel_4lang/results/internvl35_rstem_ropts
mkdir -p "$OUT/logs"

status() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/STATUS"; }
trap 'status "FAILED at stage ${CURRENT:-?} (exit $?). See $OUT/logs/"' ERR

preflight() {
  CURRENT=preflight
  python - <<'PY'
import hashlib, json, sys
from pathlib import Path
cfg = Path("01_code/configs/models/internvl3_5_8b_4090.yaml")
assert hashlib.sha256(cfg.read_bytes()).hexdigest() == \
    "7fed517cf7905dd8158487e25754b716c48c31c55b91469381d0332e4beebf03", "Model config differs from the 2026-11-09 run"
sys.path.insert(0, "01_code/src")
from mpr_crosslocale.inference.run_rel_followup import code_identity
old = json.loads(Path("followup_rel_4lang/rstem_ropts_inputs/run_contract_internvl35_rel_20261109.json").read_text())
diff = sorted(k for k in set(code_identity()) | set(old["code_sha256"]) if old["code_sha256"].get(k) != code_identity().get(k))
assert not diff, f"Inference code differs from the 2026-11-09 InternVL run: {diff}"
import torch, transformers, timm
name = torch.cuda.get_device_name(0)
assert torch.cuda.device_count() == 1 and "4090" in name, name
want = old["software_versions"]
for pkg, have in (("torch", torch.__version__), ("transformers", transformers.__version__), ("timm", timm.__version__)):
    assert have == want[pkg], f"{pkg} {have} differs from 2026-11-09 run {want[pkg]}"
from huggingface_hub import snapshot_download
snap = snapshot_download(old["model_config"]["model_id"], revision=old["model_config"]["revision"], local_files_only=True)
assert Path(snap, "config.json").is_file(), snap
print("GPU", name, "| torch", torch.__version__, "| model", snap)
PY
  python followup_rel_4lang/data_bundle.py verify > "$OUT/logs/bundle_verify.log"
  python followup_rel_4lang/run_rel_mixed_internvl.py --model-config "$MODEL_CONFIG" \
    --output-dir "$OUT/dry_run" --dry-run > "$OUT/logs/dry_run.log"
  status "preflight passed"
}

run_smoke() {
  CURRENT=smoke
  status "smoke started"
  python followup_rel_4lang/run_rel_mixed_internvl.py --model-config "$MODEL_CONFIG" \
    --split main --max-items 3 --batch-size 1 --resume \
    --output-dir "$OUT/smoke" 2>&1 | tee -a "$OUT/logs/smoke.log"
  CURRENT=smoke_gate
  python followup_rel_4lang/check_rstem_gate_internvl.py smoke "$OUT/smoke" > "$OUT/logs/smoke_gate.log"
  status "smoke passed"
}

run_full() {
  CURRENT=full
  status "full started (7,584 inferences)"
  python followup_rel_4lang/run_rel_mixed_internvl.py --model-config "$MODEL_CONFIG" \
    --split main --batch-size 1 --resume \
    --output-dir "$OUT/full" 2>&1 | tee -a "$OUT/logs/full.log"
  CURRENT=complete_gate
  python followup_rel_4lang/check_rstem_gate_internvl.py complete "$OUT/full" > "$OUT/logs/complete_gate.log"
  status "full done"
}

package() {
  CURRENT=package
  git rev-parse HEAD > "$OUT/git_commit.txt" || true
  git log --oneline -6 > "$OUT/git_log.txt" || true
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
