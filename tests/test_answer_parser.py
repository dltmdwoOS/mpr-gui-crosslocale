from mpr_crosslocale.inference.answer_parser import parse_label


def test_parse_plain_label():
    assert parse_label("B") == "B"


def test_parse_answer_prefix():
    assert parse_label("Answer: C") == "C"


def test_parse_gold_with_text():
    assert parse_label("C. Tap the shutter button") == "C"


def test_rejects_ambient_letters():
    assert parse_label("The best answer is probably C") is None
