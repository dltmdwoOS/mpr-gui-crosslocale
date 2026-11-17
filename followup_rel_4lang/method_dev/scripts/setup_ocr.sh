#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface" TORCH_HOME="$XDG_CACHE_HOME/torch" PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
TASK_PY="$TASK_REPO/.venv/bin/python"
if [[ ! -x "$TASK_PY" ]]; then
  echo '기존 Qwen 실행용 .venv가 필요합니다. method_dev/README_KO.md를 먼저 확인하세요.' >&2
  exit 1
fi
TASK_CONSTRAINTS="followup_rel_4lang/method_dev/artifacts/ocr_existing_packages.constraints.txt"
mkdir -p followup_rel_4lang/method_dev/artifacts
"$TASK_PY" - "$TASK_CONSTRAINTS" <<'PY'
import importlib.metadata as m
from pathlib import Path
import sys
from packaging.utils import canonicalize_name
required = ['torch','torchvision','numpy','transformers','accelerate']
for name in required:
    m.version(name)
# system-site-packages may expose several dist-info versions. Pin the version
# actually resolved by this interpreter, once per canonical package name.
names = {canonicalize_name(d.metadata['Name']) for d in m.distributions()}
Path(sys.argv[1]).write_text(''.join(f'{name}=={m.version(name)}\n' for name in sorted(names)))
PY
# Constrain every existing package: OCR installation cannot upgrade the VLM environment.
"$TASK_PY" -m pip install -c "$TASK_CONSTRAINTS" -r followup_rel_4lang/method_dev/requirements-ocr.txt "$@"
if [[ " $* " == *" --dry-run "* ]]; then exit 0; fi
"$TASK_PY" - <<'PY'
import easyocr
print('EasyOCR ready:', easyocr.__version__)
PY
