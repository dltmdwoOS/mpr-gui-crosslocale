#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

command -v nvidia-smi >/dev/null || {
  echo "nvidia-smi was not found."
  exit 1
}

nvidia-smi

"${PYTHON_BIN}" - <<'PY'
import shutil
from pathlib import Path

import torch
import torchvision
import transformers
from transformers import Qwen3VLForConditionalGeneration

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available.")

gpu = torch.cuda.get_device_properties(0)
free_disk = shutil.disk_usage(Path.cwd()).free / (1024**3)

print("Torch:", torch.__version__)
print("Torchvision:", torchvision.__version__)
print("Transformers:", transformers.__version__)
print("GPU:", gpu.name)
print(f"GPU memory: {gpu.total_memory / (1024**3):.1f} GiB")
print(f"Free disk: {free_disk:.1f} GiB")
print("Qwen3-VL class:", Qwen3VLForConditionalGeneration.__name__)

if gpu.total_memory < 16 * 1024**3:
    raise SystemExit("At least 16 GiB GPU memory is required; 24 GiB or more is recommended.")
if free_disk < 25:
    raise SystemExit("At least 25 GiB of free disk is required; 40 GiB or more is recommended.")
PY
