from mpr_crosslocale.data.parallel_index import canonical_state_key, parallel_sample_id


def test_canonical_state_key_removes_language_markers():
    assert canonical_state_key("../images/6/en/camera_en_8.jpg") == "6/camera_8.jpg"
    assert canonical_state_key("images/6/ja/camera_ja_8.jpg") == "6/camera_8.jpg"
    assert canonical_state_key("images/6/zh/camera_zh_8.jpg") == "6/camera_8.jpg"


def test_parallel_sample_id_prefixes_dimension():
    assert parallel_sample_id("ap", "images/6/en/camera_en_8.jpg") == "ap::6/camera_8.jpg"
