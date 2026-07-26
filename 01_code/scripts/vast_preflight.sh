#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
MODEL_CONFIG="${MODEL_CONFIG:-configs/models/qwen2_5_vl_7b.yaml}"
export MODEL_CONFIG

test -s "${MODEL_CONFIG}" || {
  echo "Model config not found: ${MODEL_CONFIG}"
  exit 1
}

command -v nvidia-smi >/dev/null || {
  echo "nvidia-smi was not found."
  exit 1
}

nvidia-smi

"${PYTHON_BIN}" - <<'PY'
import os
import shutil
from pathlib import Path

import google.protobuf
import sentencepiece
import timm
import torch
import torchvision
import transformers
import yaml
from transformers import Qwen3VLForConditionalGeneration

model_config_path = Path(os.environ.get("MODEL_CONFIG", "configs/models/qwen2_5_vl_7b.yaml"))
model_config = yaml.safe_load(model_config_path.read_text(encoding="utf-8"))
model_family = model_config.get("model_family")

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available.")

gpu = torch.cuda.get_device_properties(0)
free_disk = shutil.disk_usage(Path.cwd()).free / (1024**3)

print("Torch:", torch.__version__)
print("Torchvision:", torchvision.__version__)
print("Transformers:", transformers.__version__)
print("timm:", timm.__version__)
print("Protobuf:", google.protobuf.__version__)
print("SentencePiece:", sentencepiece.__version__)
print("Model config:", model_config_path)
print("Model family:", model_family)
print("GPU:", gpu.name)
print(f"GPU memory: {gpu.total_memory / (1024**3):.1f} GiB")
print(f"Free disk: {free_disk:.1f} GiB")
print("Qwen3-VL class:", Qwen3VLForConditionalGeneration.__name__)
if model_family == "internvl2_5":
    if not model_config.get("revision"):
        raise SystemExit("InternVL remote-code revision must be pinned.")
    if not model_config.get("trust_remote_code"):
        raise SystemExit("InternVL2.5 requires trust_remote_code: true.")
    if sentencepiece.__version__ != "0.2.0":
        raise SystemExit(
            "InternVL2.5 requires sentencepiece==0.2.0; "
            f"found {sentencepiece.__version__}."
        )
    print("InternVL2.5 dependency and revision checks: ready")
    print("InternVL2.5 model weights were not downloaded")

if gpu.total_memory < 16 * 1024**3:
    raise SystemExit("At least 16 GiB GPU memory is required; 24 GiB or more is recommended.")
if free_disk < 25:
    raise SystemExit("At least 25 GiB of free disk is required; 40 GiB or more is recommended.")
PY
