#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mpr-gui-crosslocale
source .venv/bin/activate
export XDG_CACHE_HOME="$PWD/.cache"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
source followup_rel_4lang/qwen3_4090_env.sh
export MODEL_CONFIG=01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml
export DESCRIPTORS=followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json
BATCH=$(python - <<'PY'
import hashlib,json,os
from pathlib import Path
p=Path('followup_rel_4lang/results/qwen3_single4090/batch_selection.json')
r=json.loads(p.read_text())
assert r['selected_batch_size'] in (3,4), 'Batch check failed'
assert r['config_sha256']==hashlib.sha256(Path(os.environ['MODEL_CONFIG']).read_bytes()).hexdigest(), 'Config changed since batch check'
assert r['manifest_sha256']==hashlib.sha256(Path('01_code/data/manifests/mpr_gui_manifest.jsonl').read_bytes()).hexdigest(), 'Manifest changed since batch check'
assert '4090' in r['gpu']
print(r['selected_batch_size'])
PY
)
export BATCH
echo "Fixed batch: $BATCH"
python 01_code/run_cross_locale.py \
  --manifest 01_code/data/manifests/mpr_gui_manifest.jsonl --repo-root 01_code \
  --model-config "$MODEL_CONFIG" --dimensions wf wi au ap ael rel \
  --sample-unit semantic_items --seed 42 --batch-size "$BATCH" \
  --score-labels --system-prompt-mode english_fixed --device-map cuda:0 --resume \
  --output followup_rel_4lang/results/qwen3_single4090/full_6x6.jsonl \
  --failures-out followup_rel_4lang/results/qwen3_single4090/full_6x6_failures.jsonl \
  --sample-manifest-out followup_rel_4lang/results/qwen3_single4090/full_6x6_plan.json \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/full_6x6.log
python -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input followup_rel_4lang/results/qwen3_single4090/full_6x6.jsonl \
  --json-out followup_rel_4lang/results/qwen3_single4090/full_6x6_summary.json \
  --csv-out followup_rel_4lang/results/qwen3_single4090/full_6x6_summary.csv

python followup_rel_4lang/run_inference.py \
  --model-config "$MODEL_CONFIG" --batch-size "$BATCH" --strict-batch-size --resume \
  --output-dir followup_rel_4lang/results/qwen3_single4090/full_rel \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/full_rel.log

python followup_rel_4lang/grounding_eval/run_qwen3_grounding.py \
  --model-path "$MODEL_SNAPSHOT" --suite main --descriptors "$DESCRIPTORS" \
  --batch-size "$BATCH" --max-pixels 2097152 --patch-embed-memory-format channels_last_3d \
  --output-dir followup_rel_4lang/results/qwen3_single4090/grounding_main_orcf \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/grounding_main_orcf.log
