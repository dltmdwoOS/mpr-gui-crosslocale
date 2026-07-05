from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mpr_crosslocale.inference.prompts import build_prompt_text


@dataclass(frozen=True)
class QwenGenerateOutput:
    raw_output: str
    rendered_prompt: str
    prompt_token_count: int
    output_token_count: int


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
    """Transformers backend for Qwen2.5-VL multiple-choice inference."""

    model_id = "Qwen/Qwen2.5-VL-7B-Instruct"

    def __init__(
        self,
        model_id: str = model_id,
        revision: str | None = None,
        dtype: str = "bfloat16",
        attn_implementation: str | None = "flash_attention_2",
        device_map: str | dict[str, Any] | None = "auto",
        processor_kwargs: dict[str, Any] | None = None,
    ) -> None:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        model_kwargs: dict[str, Any] = {
            "revision": revision,
            "torch_dtype": _torch_dtype(dtype),
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
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            **model_kwargs,
        )

    @staticmethod
    def build_messages(input_row: dict[str, Any], prompt_profile: str) -> list[dict[str, Any]]:
        content: list[dict[str, str]] = []
        for image_path in input_row["image_paths"]:
            content.append({"type": "image", "image": Path(image_path).as_posix()})
        content.append(
            {
                "type": "text",
                "text": build_prompt_text(str(input_row["question_raw"]), prompt_profile),
            }
        )
        return [{"role": "user", "content": content}]

    def generate_one(
        self,
        input_row: dict[str, Any],
        prompt_profile: str,
        generation_config: dict[str, Any],
    ) -> QwenGenerateOutput:
        import torch
        from qwen_vl_utils import process_vision_info

        messages = self.build_messages(input_row, prompt_profile)
        rendered_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[rendered_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        generation_kwargs = _clean_generation_kwargs(generation_config)

        with torch.inference_mode():
            generated_ids = self.model.generate(**inputs, **generation_kwargs)

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
        )
