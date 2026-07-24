from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mpr_crosslocale.inference.constrained_choice import LABELS
from mpr_crosslocale.inference.label_scoring import LabelScoreSummary, summarize_label_logprobs
from mpr_crosslocale.inference.prompts import build_prompt_text


@dataclass(frozen=True)
class QwenGenerateOutput:
    raw_output: str
    rendered_prompt: str
    prompt_token_count: int
    output_token_count: int
    label_summary: LabelScoreSummary | None = None


def _torch_dtype(dtype_name: str):
    import torch

    aliases = {
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    return aliases[dtype_name]


def _clean_generation_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if value is not None}


class Qwen25VLAdapter:
    """Transformers backend for Qwen2.5-VL and Qwen3-VL inference."""

    model_id = "Qwen/Qwen2.5-VL-7B-Instruct"

    def __init__(
        self,
        model_id: str = model_id,
        revision: str | None = None,
        dtype: str = "bfloat16",
        attn_implementation: str | None = "flash_attention_2",
        device_map: str | dict[str, Any] | None = "auto",
        processor_kwargs: dict[str, Any] | None = None,
        model_family: str = "qwen2_5_vl",
    ) -> None:
        from transformers import AutoProcessor

        model_class = _model_class(model_family)

        model_kwargs: dict[str, Any] = {
            "revision": revision,
            "dtype": _torch_dtype(dtype),
            "device_map": device_map,
        }
        if attn_implementation:
            model_kwargs["attn_implementation"] = attn_implementation
        model_kwargs = _clean_generation_kwargs(model_kwargs)
        processor_kwargs = _clean_generation_kwargs(processor_kwargs or {})

        self.model_id = model_id
        self.revision = revision
        self.processor = AutoProcessor.from_pretrained(
            model_id,
            revision=revision,
            **processor_kwargs,
        )
        self.model = model_class.from_pretrained(
            model_id,
            **model_kwargs,
        )
        self.model_family = model_family

    @staticmethod
    def build_messages(
        input_row: dict[str, Any],
        prompt_profile: str,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, str]] = []
        for image_path in input_row["image_paths"]:
            content.append({"type": "image", "image": Path(image_path).as_posix()})
        content.append(
            {
                "type": "text",
                "text": build_prompt_text(str(input_row["question_raw"]), prompt_profile),
            }
        )
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})
        messages.append({"role": "user", "content": content})
        return messages

    def generate_one(
        self,
        input_row: dict[str, Any],
        prompt_profile: str,
        generation_config: dict[str, Any],
        system_prompt: str | None = None,
        score_labels: bool = False,
    ) -> QwenGenerateOutput:
        import torch
        from qwen_vl_utils import process_vision_info

        messages = self.build_messages(input_row, prompt_profile, system_prompt=system_prompt)
        rendered_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(
            messages,
            **_vision_process_kwargs(self.model_family, self.processor),
        )
        inputs = self.processor(
            text=[rendered_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        generation_kwargs = _clean_generation_kwargs(generation_config)
        if score_labels:
            generation_kwargs["return_dict_in_generate"] = True
            generation_kwargs["output_logits"] = True

        with torch.inference_mode():
            generation_output = self.model.generate(**inputs, **generation_kwargs)

        label_summary = None
        if score_labels:
            generated_ids = generation_output.sequences
            if not generation_output.logits:
                raise RuntimeError("Generation did not return first-step logits for label scoring")
            label_summary = self._summarize_label_logits(
                generation_output.logits[0][0],
                input_row,
            )
        else:
            generated_ids = generation_output

        prompt_len = int(inputs.input_ids.shape[1])
        generated_trimmed = generated_ids[:, prompt_len:]
        decoded = self.processor.batch_decode(
            generated_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return QwenGenerateOutput(
            raw_output=decoded[0].strip(),
            rendered_prompt=rendered_prompt,
            prompt_token_count=prompt_len,
            output_token_count=int(generated_trimmed.shape[1]),
            label_summary=label_summary,
        )

    def score_labels(
        self,
        input_row: dict[str, Any],
        prompt_profile: str,
        system_prompt: str | None = None,
    ):
        import torch
        from qwen_vl_utils import process_vision_info

        messages = self.build_messages(input_row, prompt_profile, system_prompt=system_prompt)
        rendered_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(
            messages,
            **_vision_process_kwargs(self.model_family, self.processor),
        )
        inputs = self.processor(
            text=[rendered_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)

        with torch.inference_mode():
            outputs = self.model(**inputs)
            next_token_logits = outputs.logits[0, -1, :]

        return self._summarize_label_logits(next_token_logits, input_row)

    def _summarize_label_logits(
        self,
        next_token_logits: Any,
        input_row: dict[str, Any],
    ) -> LabelScoreSummary:
        import torch

        label_token_ids = self._label_token_ids()
        if any(len(ids) != 1 for ids in label_token_ids.values()):
            raise ValueError("A/B/C/D labels are not single-token under this tokenizer")
        log_probs = torch.nn.functional.log_softmax(next_token_logits, dim=-1)
        label_logprobs = {
            label: float(log_probs[token_ids[0]].detach().cpu())
            for label, token_ids in label_token_ids.items()
        }
        return summarize_label_logprobs(
            label_logprobs,
            gold_label=str(input_row["gold_label"]),
            scoring_method="next_token_single_label",
            label_token_ids=label_token_ids,
        )

    def _label_token_ids(self) -> dict[str, list[int]]:
        token_ids: dict[str, list[int]] = {}
        for label in LABELS:
            ids = self.processor.tokenizer.encode(label, add_special_tokens=False)
            token_ids[label] = list(ids)
        return token_ids


def _model_class(model_family: str):
    try:
        if model_family == "qwen2_5_vl":
            from transformers import Qwen2_5_VLForConditionalGeneration

            return Qwen2_5_VLForConditionalGeneration
        if model_family == "qwen3_vl":
            from transformers import Qwen3VLForConditionalGeneration

            return Qwen3VLForConditionalGeneration
    except ImportError as exc:
        raise ImportError(
            f"The installed transformers package does not support {model_family!r}. "
            "Install a transformers release that provides the corresponding Qwen VL model class."
        ) from exc
    raise ValueError(f"Unsupported Qwen model_family: {model_family!r}")


def _vision_process_kwargs(model_family: str, processor: Any) -> dict[str, Any]:
    if model_family != "qwen3_vl":
        return {}
    image_processor = getattr(processor, "image_processor", None)
    patch_size = getattr(image_processor, "patch_size", 16)
    return {"image_patch_size": int(patch_size)}
