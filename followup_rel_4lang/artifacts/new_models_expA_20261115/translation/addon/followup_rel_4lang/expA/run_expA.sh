#!/usr/bin/env bash
# Experiment A (O, T, R) on ONE RTX 4090. Run from the repo root of the earlier R_stem/R_opts setup
# of the same model (Qwen3: mpr-gui-crosslocale, InternVL3.5: mpr-ivl), inside tmux:
#   bash followup_rel_4lang/expA/run_expA.sh qwen3 all        # preflight -> smoke (108) -> gate -> full (5,688) -> gate -> package
#   bash followup_rel_4lang/expA/run_expA.sh internvl35 all
# Stages: smoke | full | all. Rerunning the same command resumes. Progress: cat $OUT/STATUS
set -Eeuo pipefail
MODEL="${1:?Give qwen3 or internvl35}"
STAGE="${2:?Give smoke, full or all}"
cd "$(dirname "$0")/../.."
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$PWD/.cache}"
export HF_HOME="${HF_HOME:-$XDG_CACHE_HOME/huggingface}"
source .venv/bin/activate
case "$MODEL" in
  qwen3) source followup_rel_4lang/qwen3_4090_env.sh
         MODEL_CONFIG=01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml
         CFG_SHA=2775bb6b981d35922c46545ef58af0ac8e8ded1a3615902c73ac141609adbc8b
         CONTRACT=followup_rel_4lang/rstem_ropts_inputs/run_contract_qwen3_rel_20261107.json
         PKGS="torch transformers"; BATCH=3 ;;
  internvl35) source followup_rel_4lang/internvl35_4090_env.sh
         MODEL_CONFIG=01_code/configs/models/internvl3_5_8b_4090.yaml
         CFG_SHA=7fed517cf7905dd8158487e25754b716c48c31c55b91469381d0332e4beebf03
         CONTRACT=followup_rel_4lang/rstem_ropts_inputs/run_contract_internvl35_rel_20261109.json
         PKGS="torch transformers timm"; BATCH=1 ;;
  *) echo "Unknown model: $MODEL"; exit 1 ;;
esac
OUT=followup_rel_4lang/results/expA_${MODEL}
mkdir -p "$OUT/logs"
export MODEL_CONFIG CFG_SHA CONTRACT PKGS

status() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/STATUS"; }
trap 'status "FAILED at stage ${CURRENT:-?} (exit $?). See $OUT/logs/"' ERR

preflight() {
  CURRENT=preflight
  (cd followup_rel_4lang/expA && sha256sum -c expA_inputs/EXPA_SHA256SUMS) > "$OUT/logs/addon_verify.log"
  python - <<'PY'
import hashlib, json, os, sys
from pathlib import Path
cfg = Path(os.environ["MODEL_CONFIG"])
assert hashlib.sha256(cfg.read_bytes()).hexdigest() == os.environ["CFG_SHA"], "Model config differs from the earlier run"
sys.path.insert(0, "01_code/src")
from mpr_crosslocale.inference.run_rel_followup import code_identity
old = json.loads(Path(os.environ["CONTRACT"]).read_text())
now = code_identity()
diff = sorted(k for k in set(now) | set(old["code_sha256"]) if old["code_sha256"].get(k) != now.get(k))
assert not diff, f"Inference code differs from the earlier run: {diff}"
import importlib, torch
name = torch.cuda.get_device_name(0)
assert torch.cuda.device_count() == 1 and "4090" in name, name
for pkg in os.environ["PKGS"].split():
    have = importlib.import_module(pkg).__version__
    assert have == old["software_versions"][pkg], f"{pkg} {have} differs from earlier run {old['software_versions'][pkg]}"
from huggingface_hub import snapshot_download
snap = snapshot_download(old["model_config"]["model_id"], revision=old["model_config"]["revision"], local_files_only=True)
assert Path(snap, "config.json").is_file(), snap
print("GPU", name, "| torch", torch.__version__, "| model", snap)
PY
  python followup_rel_4lang/data_bundle.py verify > "$OUT/logs/bundle_verify.log"
  python followup_rel_4lang/expA/run_rel_T.py --model "$MODEL" --batch-size "$BATCH" --model-config "$MODEL_CONFIG" \
    --output-dir "$OUT/dry_run" --dry-run > "$OUT/logs/dry_run.log"
  status "preflight passed"
}

run_smoke() {
  CURRENT=smoke
  status "smoke started (108 inferences)"
  python followup_rel_4lang/expA/run_rel_T.py --model "$MODEL" --batch-size "$BATCH" --model-config "$MODEL_CONFIG" \
    --split main --max-items 3 --resume --output-dir "$OUT/smoke" 2>&1 | tee -a "$OUT/logs/smoke.log"
  CURRENT=smoke_gate
  python followup_rel_4lang/expA/check_T_gate.py "$MODEL" smoke "$OUT/smoke" > "$OUT/logs/smoke_gate.log"
  status "smoke passed"
}

run_full() {
  CURRENT=full
  status "full started (5,688 inferences)"
  python followup_rel_4lang/expA/run_rel_T.py --model "$MODEL" --batch-size "$BATCH" --model-config "$MODEL_CONFIG" \
    --split main --resume --output-dir "$OUT/full" 2>&1 | tee -a "$OUT/logs/full.log"
  CURRENT=complete_gate
  python followup_rel_4lang/expA/check_T_gate.py "$MODEL" complete "$OUT/full" > "$OUT/logs/complete_gate.log"
  status "full done"
}

package() {
  CURRENT=package
  git rev-parse HEAD > "$OUT/git_commit.txt" || true
  git log --oneline -6 > "$OUT/git_log.txt" || true
  git status --short > "$OUT/git_status.txt" || true
  python -m pip freeze > "$OUT/requirements.freeze.txt"
  nvidia-smi > "$OUT/nvidia_smi.txt" || true
  cp followup_rel_4lang/expA/expA_inputs/expA_lock.json "$OUT/"
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
