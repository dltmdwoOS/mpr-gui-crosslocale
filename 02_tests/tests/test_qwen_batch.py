from types import SimpleNamespace

import pytest
import torch

from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter


class TensorInputs(dict):
    def __getattr__(self, name):
        return self[name]

    def to(self, device):
        return self


def fake_adapter(monkeypatch, score_labels=True):
    import qwen_vl_utils

    rows = [
        {"question_raw": "Short?", "gold_label": "A", "image_paths": ["one.png"]},
        {"question_raw": "A longer question?", "gold_label": "C", "image_paths": ["two.png", "three.png"]},
    ]
    seen = {}

    def vision_info(messages, **kwargs):
        assert len(messages) == 2
        assert all(conversation[0]["role"] == "system" for conversation in messages)
        paths = [
            item["image"] for conversation in messages
            for message in conversation for item in message["content"] if item["type"] == "image"
        ]
        assert paths == ["one.png", "two.png", "three.png"]
        return paths, None

    monkeypatch.setattr(qwen_vl_utils, "process_vision_info", vision_info)

    class Processor:
        tokenizer = SimpleNamespace(
            padding_side="right", encode=lambda label, add_special_tokens: [ord(label)],
        )

        def apply_chat_template(self, messages, **kwargs):
            return messages[-1]["content"][-1]["text"]

        def __call__(self, **kwargs):
            assert self.tokenizer.padding_side == "left"
            assert kwargs["images"] == ["one.png", "two.png", "three.png"]
            assert kwargs["text"][0] != kwargs["text"][1]
            assert kwargs["padding"] and kwargs["return_tensors"] == "pt"
            return TensorInputs(
                input_ids=torch.tensor([[0, 0, 10, 11], [10, 11, 12, 13]]),
                attention_mask=torch.tensor([[0, 0, 1, 1], [1, 1, 1, 1]]),
            )

        def batch_decode(self, generated, **kwargs):
            # Both rows must be trimmed after the common padded prompt width.
            assert generated == [[ord("A"), 99, 0], [ord("C"), 98, 99]]
            return [" A ", " C "]

    class Model:
        device = "cpu"
        generation_config = SimpleNamespace(eos_token_id=[98, 99])

        def generate(self, **kwargs):
            seen["calls"] = seen.get("calls", 0) + 1
            assert kwargs["max_new_tokens"] == 3
            assert kwargs.get("output_logits", False) == score_labels
            sequences = torch.cat([
                kwargs["input_ids"], torch.tensor([[ord("A"), 99, 0], [ord("C"), 98, 99]]),
            ], dim=1)
            if not score_labels:
                return sequences
            logits = torch.full((2, 128), -10.0)
            logits[0, ord("A")] = 3.0
            logits[1, ord("C")] = 2.0
            return SimpleNamespace(sequences=sequences, logits=[logits])

    adapter = object.__new__(Qwen25VLAdapter)
    adapter.processor, adapter.model = Processor(), Model()
    adapter.model_family = "qwen2_5_vl"
    return adapter, rows, seen


@pytest.mark.parametrize("score_labels", [False, True])
def test_batch_preserves_image_output_and_logit_alignment(monkeypatch, score_labels):
    adapter, rows, seen = fake_adapter(monkeypatch, score_labels)
    outputs = adapter.generate_batch(
        rows, "mpr_label_only_v1", {"max_new_tokens": 3}, "Fixed system", score_labels,
    )
    assert seen["calls"] == 1
    assert [output.raw_output for output in outputs] == ["A", "C"]
    assert [output.prompt_token_count for output in outputs] == [2, 4]
    assert [output.output_token_count for output in outputs] == [2, 2]
    if score_labels:
        assert [output.label_summary.scored_predicted_label for output in outputs] == ["A", "C"]
        assert all(output.label_summary.gold_rank == 1 for output in outputs)
    else:
        assert all(output.label_summary is None for output in outputs)


def test_batch_scores_match_individual_first_token_scores():
    adapter = object.__new__(Qwen25VLAdapter)
    adapter.processor = SimpleNamespace(
        tokenizer=SimpleNamespace(encode=lambda label, add_special_tokens: [ord(label)]),
    )
    logits = torch.arange(256, dtype=torch.float32).reshape(2, 128) / 50
    rows = [{"gold_label": "D"}, {"gold_label": "B"}]
    batch = adapter._summarize_label_logits_batch(logits, rows)
    individual = [adapter._summarize_label_logits(logit, row) for logit, row in zip(logits, rows)]
    assert batch == individual


def test_batch_missing_logits_fails_instead_of_dropping_scores(monkeypatch):
    adapter, rows, seen = fake_adapter(monkeypatch)
    original = adapter.model.generate

    def missing_logits(**kwargs):
        result = original(**kwargs)
        result.logits = []
        return result

    adapter.model.generate = missing_logits
    with pytest.raises(RuntimeError, match="first-step logits"):
        adapter.generate_batch(rows, "mpr_label_only_v1", {"max_new_tokens": 3}, "Fixed system", True)
