from mpr_crosslocale.data.schema import LANGUAGES, LABELS


def test_supported_languages_and_labels():
    assert LANGUAGES == ("en", "zh", "fr", "ru", "ja", "th")
    assert LABELS == ("A", "B", "C", "D")
