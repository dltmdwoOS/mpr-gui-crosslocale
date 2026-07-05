from mpr_crosslocale.data.options import parse_question_options


def test_parse_standard_options():
    parsed = parse_question_options("Question? A: Alpha B: Beta C: Gamma D: Delta")

    assert parsed.option_parse_status == "ok"
    assert parsed.question_stem == "Question?"
    assert parsed.option_order == ["A", "B", "C", "D"]
    assert parsed.options["C"] == "Gamma"


def test_parse_nonstandard_option_order():
    parsed = parse_question_options("Question? C: Gamma A: Alpha B: Beta D: Delta")

    assert parsed.option_parse_status == "ok"
    assert parsed.option_order == ["C", "A", "B", "D"]
    assert parsed.options["A"] == "Alpha"


def test_does_not_treat_temperature_unit_as_option():
    parsed = parse_question_options(
        "Question? A: Tap Celsius (°C). B: Tap Fahrenheit (°F). C: Open settings. D: Close."
    )

    assert parsed.option_parse_status == "ok"
    assert parsed.option_order == ["A", "B", "C", "D"]
    assert "°C" in parsed.options["A"]
