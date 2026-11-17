#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface" TORCH_HOME="$XDG_CACHE_HOME/torch" PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3
TASK_ENV="$TASK_REPO/.venv-ocr-gpu"
TASK_ROOT=followup_rel_4lang/method_dev
"$TASK_REPO/.venv/bin/python" - <<'PY'
import easyocr, torch
assert easyocr.__version__ == '1.7.2'
assert torch.cuda.is_available(), 'CUDA is required'
PY
if [[ ! -x "$TASK_ENV/bin/python" ]]; then
  "$TASK_REPO/.venv/bin/python" -m venv --system-site-packages "$TASK_ENV"
fi
mkdir -p "$TASK_ROOT/artifacts"
"$TASK_ENV/bin/python" - "$TASK_ROOT/artifacts/gpu_ocr_existing.constraints.txt" <<'PY'
import importlib.metadata as m
from packaging.utils import canonicalize_name
from pathlib import Path
import sys
names = {canonicalize_name(d.metadata['Name']) for d in m.distributions()}
# opt-einsum is an isolated Paddle dependency; never change the shared installation.
names.discard('opt-einsum')
Path(sys.argv[1]).write_text(''.join(f'{n}=={m.version(n)}\n' for n in sorted(names)))
PY
"$TASK_ENV/bin/python" -m pip install -c "$TASK_ROOT/artifacts/gpu_ocr_existing.constraints.txt" -r "$TASK_ROOT/requirements-ocr-gpu.txt"
# Reuse CUDA13/cuDNN libraries already supplied by this lab's PyTorch environment.
# A real CUDA smoke test below verifies this instead of trusting the package name.
"$TASK_ENV/bin/python" -m pip install --no-deps --index-url https://www.paddlepaddle.org.cn/packages/stable/cu130/ paddlepaddle-gpu==3.3.0
"$TASK_ENV/bin/python" "$TASK_ROOT/scripts/prepare_gpu_ocr_models.py"
"$TASK_REPO/.venv/bin/python" "$TASK_ROOT/scripts/run_gpu_ocr_screen.py"
