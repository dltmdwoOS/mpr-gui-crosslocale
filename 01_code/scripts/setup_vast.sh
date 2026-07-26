#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

"${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel
"${PYTHON_BIN}" -m pip install -e ".[models]"

"${PYTHON_BIN}" - <<'PY'
import accelerate
import google.protobuf
import qwen_vl_utils
import sentencepiece
import timm
import torch
import torchvision
import transformers
from transformers import Qwen3VLForConditionalGeneration

print("Environment ready")
print("Transformers:", transformers.__version__)
print("Accelerate:", accelerate.__version__)
print("Torchvision:", torchvision.__version__)
print("timm:", timm.__version__)
print("Protobuf:", google.protobuf.__version__)
print("SentencePiece:", sentencepiece.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Qwen3-VL class:", Qwen3VLForConditionalGeneration.__name__)
print("InternVL2.5 dependencies: ready (model weights were not downloaded)")
PY
