from mpr_crosslocale.data.pair_builder import build_cross_locale_pair_rows


def test_build_cross_locale_pair_rows():
    index = {
        "languages": ["en", "ja"],
        "entries": [
            {
                "parallel_id": "wf::1/foo_1.jpg",
                "complete": True,
                "gold_labels_consistent": True,
                "samples": {
                    "en": {
                        "sample_id": "wf::1/foo_1.jpg::en",
                        "asset": "../images/1/en/foo_en_1.jpg",
                        "gold_label": "A",
                    },
                    "ja": {
                        "sample_id": "wf::1/foo_1.jpg::ja",
                        "asset": "../images/1/ja/foo_ja_1.jpg",
                        "gold_label": "A",
                    },
                },
            }
        ],
    }

    rows = build_cross_locale_pair_rows(index)

    assert len(rows) == 2
    assert rows[0]["question_language"] == "en"
    assert rows[0]["gui_language"] == "ja"
    assert rows[0]["question_sample_id"] == "wf::1/foo_1.jpg::en"
    assert rows[0]["mismatch_gui_sample_id"] == "wf::1/foo_1.jpg::ja"
    assert rows[0]["oracle_gui_sample_id"] == "wf::1/foo_1.jpg::en"
