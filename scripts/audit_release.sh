#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
python -m mpr_crosslocale.data.validate_release "$@"
python -m mpr_crosslocale.data.build_manifest "$@"
python -m mpr_crosslocale.data.validate_manifests
