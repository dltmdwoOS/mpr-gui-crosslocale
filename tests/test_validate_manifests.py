from pathlib import Path

import pytest

from mpr_crosslocale.data.validate_manifests import validate_all


def test_current_public_release_manifests_if_present():
    manifest = Path("data/manifests/mpr_gui_manifest.jsonl")
    parallel = Path("data/manifests/parallel_index.json")
    pairs = Path("data/manifests/cross_locale_pairs.jsonl")
    canonical = Path("data/manifests/canonical_inputs.jsonl")
    mismatch = Path("data/manifests/mismatch_inputs.jsonl")
    raw_root = Path("data/raw/mpr_gui_bench")
    if not (manifest.exists() and parallel.exists() and pairs.exists() and canonical.exists() and mismatch.exists()):
        pytest.skip("Public release manifests are not generated in this checkout.")
    if not raw_root.exists():
        pytest.skip("Raw MPR-GUI data is not present in this checkout.")

    result = validate_all(manifest, parallel, pairs, canonical, mismatch)

    assert result["ok"], result["errors"][:10]
    assert result["summary"] == {
        "manifest_rows": 13470,
        "parallel_ids": 2245,
        "directed_mismatch_pairs": 67350,
        "canonical_inputs": 13470,
        "mismatch_inputs": 67350,
    }
