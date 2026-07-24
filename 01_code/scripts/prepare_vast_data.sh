#!/usr/bin/env bash
set -euo pipefail

scripts/download_mpr_gui.sh \
  --source-lock data/manifests/source_lock.json

scripts/audit_release.sh

test -s data/manifests/mpr_gui_manifest.jsonl
echo "Manifest ready: data/manifests/mpr_gui_manifest.jsonl"
