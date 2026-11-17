#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
TASK_FLAGS=()
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 1 || "$1" != '--mock' ]]; then
    echo 'Usage: bash run_ocr_8b_then_4b.sh [--mock]' >&2
    exit 2
  fi
  TASK_FLAGS=(--mock)
fi
echo 'PHASE 1/2: resume remaining Qwen3-VL-8B OCR experiment'
bash followup_rel_4lang/method_dev/scripts/run_ocr_remaining.sh --run "${TASK_FLAGS[@]}"
echo 'PHASE 2/2: evaluate identical OCR-localized questions with Qwen3-VL-4B (all cohorts)'
exec bash followup_rel_4lang/method_dev/scripts/run_ocr_4b.sh --run "${TASK_FLAGS[@]}"
