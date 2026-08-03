#!/usr/bin/env bash
set -euo pipefail

tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
manifest="$tool_dir/data/pilot_manifest.json"
python_bin="${PYTHON_BIN:-python3}"

if [[ ! -f "$manifest" ]]; then
  echo "Pilot data가 없습니다. 먼저 prepare_pilot.py를 실행하세요." >&2
  exit 1
fi

arguments=(
  "$tool_dir/app.py"
  --open-browser
  --port 8765
)

if [[ -n "${1:-}" ]]; then
  arguments+=(--annotator "$1")
fi

echo "REL annotation server: http://127.0.0.1:8765"
echo "종료할 때 이 터미널에서 Ctrl+C를 누르세요."
exec "$python_bin" "${arguments[@]}"
