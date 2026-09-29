#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python}"
DATA_ROOT="${DATA_ROOT:-followup_rel_4lang}"
RESULTS_ROOT="${RESULTS_ROOT:-followup_rel_4lang/results}"
STAGE="${1:-smoke}"
case "$STAGE" in
  smoke) ITEM_ARGS=(--max-items 2) ;;
  full) ITEM_ARGS=() ;;
  *) echo "Usage: bash followup_rel_4lang/run_b200.sh [smoke|full]"; exit 2 ;;
esac

export TOKENIZERS_PARALLELISM=false
"$PYTHON_BIN" - <<'PY'
import torch
import torchvision
import transformers
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable")
gpu = torch.cuda.get_device_properties(0)
print("Torch:", torch.__version__, "CUDA runtime:", torch.version.cuda)
print("Torchvision:", torchvision.__version__, "Transformers:", transformers.__version__)
print("GPU:", gpu.name, "GiB:", round(gpu.total_memory / 2**30, 2))
print("Device capability:", torch.cuda.get_device_capability(0))
print("Compiled architectures:", torch.cuda.get_arch_list())
if not transformers.__version__.startswith("4.57."):
    raise SystemExit("Use the existing Transformers 4.57.x model adapter environment")
# An actual operation checks driver/kernel compatibility (also on a MIG slice).
x = torch.ones((32, 32), device="cuda", dtype=torch.bfloat16)
y = x @ x
torch.cuda.synchronize()
if y[0, 0].item() != 32:
    raise SystemExit("CUDA bfloat16 matrix multiplication failed")
PY

# Separate processes release the first model before loading the second.
for MODEL_TAG in qwen2_5_vl_7b internvl2_5_8b; do
  "$PYTHON_BIN" followup_rel_4lang/run_inference.py \
    --data-root "$DATA_ROOT" \
    --model-config "01_code/configs/models/${MODEL_TAG}.yaml" \
    --output-dir "${RESULTS_ROOT}/${STAGE}/${MODEL_TAG}" \
    "${ITEM_ARGS[@]}" --resume
done
