from pathlib import Path

from mpr_crosslocale.data.episode_loader import natural_sort_key


def test_natural_sort_orders_frame_10_after_frame_2():
    frames = [Path("frame_10.jpg"), Path("frame_2.jpg"), Path("frame_1.jpg")]
    assert [p.name for p in sorted(frames, key=natural_sort_key)] == [
        "frame_1.jpg",
        "frame_2.jpg",
        "frame_10.jpg",
    ]
