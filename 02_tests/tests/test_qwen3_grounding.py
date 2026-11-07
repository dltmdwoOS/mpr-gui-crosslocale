"""Protect prompt localization, pilot separation and item-level GPU sharding."""

from types import SimpleNamespace

import pytest
import torch
from mpr_crosslocale.models.qwen3_memory import configure_patch_embed_memory_format

from followup_rel_4lang.grounding_eval.prepare_qwen3_descriptor_review import (
    build as build_review,
)
from followup_rel_4lang.grounding_eval.run_qwen3_grounding import (
    build_groups,
    shard_for,
    summarize,
)


def test_channels_last_changes_strides_without_changing_checkpoint_values():
    projection = torch.nn.Conv3d(3, 8, kernel_size=(2, 4, 4), stride=(2, 4, 4))
    weight = projection.weight.detach().clone()
    bias = projection.bias.detach().clone()
    model = SimpleNamespace(model=SimpleNamespace(visual=SimpleNamespace(
        patch_embed=SimpleNamespace(proj=projection))))
    configure_patch_embed_memory_format(model, "channels_last_3d")
    assert projection.weight.is_contiguous(memory_format=torch.channels_last_3d)
    assert torch.equal(projection.weight, weight)
    assert torch.equal(projection.bias, bias)


def test_main_review_draft_uses_source_substrings_without_relation_questions():
    draft = build_review()
    assert draft["reviewed"] is False
    assert len(draft["descriptors"]) == 158 and len(draft["review"]) == 632
    for row in draft["review"]:
        start, end = row["source_start"], row["source_end"]
        assert row["candidate_template"].format(ref=row["reference_span"]["text"]) == row["question_stem"][start:end]
        assert "possible_relation_question_remaining" not in row["flags"]
        assert "gt_bbox" not in row and "gold_answer" not in row


def test_pilot_localizes_reference_and_context_independently():
    groups = build_groups("pilot")
    assert len(groups) == 48
    assert sum(len(g["trials"]) for g in groups) == 192
    group = next(g for g in groups if g["group_id"] == "rel::1/booking_1.jpg::en::zh")
    original, reference, context, full = group["trials"]
    assert original["marked_text"] == "blue '<ref>Search</ref>' button"
    assert reference["marked_text"] == "blue '<ref>搜索</ref>' button"
    assert context["marked_text"] == "蓝色“<ref>Search</ref>”按钮"
    assert full["marked_text"] == "蓝色“<ref>搜索</ref>”按钮"
    assert len({r["image_path"] for r in group["trials"]}) == 1
    assert len({r["image_sha256"] for r in group["trials"]}) == 1


def test_controls_are_same_language_and_change_only_target_description():
    groups = build_groups("controls")
    assert len(groups) == 16
    rows = [r for g in groups for r in g["trials"]]
    assert all(r["query_language"] == r["gui_language"] for r in rows)
    assert sum(r["condition"] == "element_only" for r in rows) == 8
    assert sum(r["condition"] == "query_informed" for r in rows) == 8
    assert all(r["marked_text"].count("<ref>") == 1 for r in rows)


def test_main_cannot_accidentally_use_pilot_descriptions():
    with pytest.raises(ValueError, match="exactly the 158"):
        build_groups("main")


def test_shards_partition_all_trials_and_keep_item_conditions_together():
    groups = build_groups("pilot")
    shards = [[g for g in groups if shard_for(g["parallel_id"], 8) == index]
              for index in range(8)]
    ids = [g["group_id"] for shard in shards for g in shard]
    assert len(ids) == len(set(ids)) == 48
    assert set(ids) == {g["group_id"] for g in groups}
    for pid in {g["parallel_id"] for g in groups}:
        assert sum(any(g["parallel_id"] == pid for g in shard) for shard in shards) == 1


def test_summary_counts_invalid_coordinates_as_misses():
    batches = [{"generate_s": 1.0, "peak_reserved_gib": 19.0, "results": [
        {"condition": "O", "gui_language": "zh", "valid_output": False, "point_in_gt_box": False},
        {"condition": "R", "gui_language": "zh", "valid_output": True, "point_in_gt_box": True},
    ]}]
    summary = summarize(batches, expected=2)
    assert summary["complete"] is False
    assert summary["conditions"]["O"] == {"count": 1, "valid": 0, "hit": 0}
    assert summary["conditions"]["R"] == {"count": 1, "valid": 1, "hit": 1}


def test_orcf_batch_packing_preserves_all_trials_and_final_remainder():
    from followup_rel_4lang.grounding_eval.run_qwen3_grounding import pack_groups
    groups = build_groups("pilot")
    expected = [r["trial_id"] for g in groups for r in g["trials"]]
    for size in (3, 4):
        batches = pack_groups(groups, size)
        actual = [r["trial_id"] for b in batches for r in b["trials"]]
        assert actual == expected and len(set(actual)) == 192
        assert all(len(b["trials"]) == size for b in batches)
    assert [len(b["trials"]) for b in pack_groups(groups[:1], 3)] == [3, 1]


def test_batch_choice_falls_back_only_on_memory_failure():
    from followup_rel_4lang.check_qwen3_batch import choose_batch
    called = []
    def probe(n):
        called.append(n)
        return {"batch_size":n,"status":"passed" if n==3 else "memory_failure"}
    assert choose_batch(probe)[0] == 3 and called == [4,3]
    assert choose_batch(lambda n:{"status":"passed"})[0] == 4
    with pytest.raises(RuntimeError, match="Both batch"):
        choose_batch(lambda n:{"status":"memory_failure"})
    with pytest.raises(RuntimeError, match="Non-memory"):
        choose_batch(lambda n:{"status":"failed"})
