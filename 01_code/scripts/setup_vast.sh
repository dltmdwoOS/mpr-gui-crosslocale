#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

"${PYTHON_BIN}" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")

try:
    import torch
    import torchvision
except ImportError as exc:
    raise SystemExit(
        "Select a Vast.ai PyTorch template that includes torch and torchvision."
    ) from exc

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available in the current Python environment.")

print("Python:", sys.version.split()[0])
print("Torch:", torch.__version__)
print("Torchvision:", torchvision.__version__)
print("CUDA:", torch.version.cuda)
print("GPU:", torch.cuda.get_device_name(0))
PY

"${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel
"${PYTHON_BIN}" -m pip install -e .
"${PYTHON_BIN}" -m pip install -r requirements-vast.txt

"${PYTHON_BIN}" - <<'PY'
import accelerate
import qwen_vl_utils
import torch
import transformers
from transformers import Qwen3VLForConditionalGeneration

print("Environment ready")
print("Transformers:", transformers.__version__)
print("Accelerate:", accelerate.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Qwen3-VL class:", Qwen3VLForConditionalGeneration.__name__)
PY
