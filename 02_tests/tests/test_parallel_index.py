from mpr_crosslocale.data.pair_builder import directed_language_pairs


def test_directed_language_pairs_skip_identity():
    pairs = directed_language_pairs(["en", "ja", "zh"])
    assert ("en", "en") not in pairs
    assert ("en", "ja") in pairs
    assert ("ja", "en") in pairs
    assert len(pairs) == 6
