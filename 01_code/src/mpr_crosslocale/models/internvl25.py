from __future__ import annotations

import json
import warnings
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from mpr_crosslocale.inference.constrained_choice import LABELS
from mpr_crosslocale.inference.label_scoring import LabelScoreSummary, summarize_label_logprobs
from mpr_crosslocale.inference.prompts import build_prompt_text

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class InternVLGenerateOutput:
    raw_output: str
    rendered_prompt: str
    prompt_token_count: int
    output_token_count: int
    label_summary: LabelScoreSummary | None = None
    num_patches_list: tuple[int, ...] = ()
    visual_token_count: int | None = None


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
    try:
        return aliases[dtype_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported dtype: {dtype_name!r}") from exc


def _clean_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if value is not None}


def ensure_generation_mixin(model: Any) -> bool:
    """Restore generation and legacy-cache support for pinned InternLM2 remote code."""
    language_model = model.language_model
    original_class = language_model.__class__
    has_generate = callable(getattr(language_model, "generate", None))
    compatible_bases: tuple[type, ...]
    if has_generate:
        compatible_bases = (original_class,)
    else:
        from transformers.generation.utils import GenerationMixin

        compatible_bases = (original_class, GenerationMixin)
    compatible_class = type(
        f"{original_class.__name__}WithLegacyGeneration",
        compatible_bases,
        {
            "_supports_default_dynamic_cache": classmethod(
                lambda cls: False
            ),
        },
    )
    language_model.__class__ = compatible_class
    if not has_generate and getattr(language_model, "generation_config", None) is None:
        from transformers.generation.configuration_utils import GenerationConfig

        language_model.generation_config = GenerationConfig.from_model_config(
            language_model.config
        )
    if not has_generate:
        warnings.warn(
            "Added Transformers GenerationMixin compatibility to InternVL2.5's "
            "legacy InternLM2 remote-code class; DynamicCache is disabled.",
            RuntimeWarning,
            stacklevel=2,
        )
    return not has_generate


def _is_usable_tokenizer(tokenizer: Any) -> bool:
    required_methods = (
        "__call__",
        "batch_decode",
        "convert_tokens_to_ids",
        "encode",
    )
    return not isinstance(tokenizer, bool) and all(
        callable(getattr(tokenizer, method, None)) for method in required_methods
    )


def load_internvl_tokenizer(
    model_id: str,
    revision: str,
    trust_remote_code: bool = True,
):
    from huggingface_hub import hf_hub_download
    from tokenizers import AddedToken
    from transformers import AutoTokenizer
    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        revision=revision,
        trust_remote_code=trust_remote_code,
        use_fast=False,
    )
    if _is_usable_tokenizer(tokenizer):
        return tokenizer
    if not trust_remote_code:
        raise TypeError(
            "InternVL2.5 tokenizer loading requires trust_remote_code=True"
        )

    tokenizer_class = get_class_from_dynamic_module(
        "tokenization_internlm2.InternLM2Tokenizer",
        model_id,
        revision=revision,
    )
    vocab_file = hf_hub_download(
        repo_id=model_id,
        filename="tokenizer.model",
        revision=revision,
    )
    tokenizer_config_path = hf_hub_download(
        repo_id=model_id,
        filename="tokenizer_config.json",
        revision=revision,
    )
    tokenizer_config = json.loads(
        Path(tokenizer_config_path).read_text(encoding="utf-8")
    )
    tokenizer_config.pop("auto_map", None)
    tokenizer_config.pop("tokenizer_class", None)
    added_tokens_decoder = tokenizer_config.get("added_tokens_decoder", {})
    tokenizer_config["added_tokens_decoder"] = {
        int(token_id): AddedToken(**token_config)
        for token_id, token_config in added_tokens_decoder.items()
    }
    tokenizer = tokenizer_class(vocab_file=vocab_file, **tokenizer_config)
    if not _is_usable_tokenizer(tokenizer):
        raise TypeError(
            f"InternVL2.5 tokenizer loader returned invalid object: {tokenizer!r}"
        )
    return tokenizer


def build_transform(input_size: int):
    import torchvision.transforms as transforms
    from torchvision.transforms.functional import InterpolationMode

    return transforms.Compose(
        [
            transforms.Lambda(lambda image: image.convert("RGB")),
            transforms.Resize(
                (input_size, input_size),
                interpolation=InterpolationMode.BICUBIC,
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )


def find_closest_aspect_ratio(
    aspect_ratio: float,
    target_ratios: list[tuple[int, int]],
    width: int,
    height: int,
    image_size: int,
) -> tuple[int, int]:
    best_ratio = (1, 1)
    best_ratio_diff = float("inf")
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            target_area = image_size * image_size * ratio[0] * ratio[1]
            if area > 0.5 * target_area:
                best_ratio = ratio
    return best_ratio


def dynamic_preprocess(
    image: Image.Image,
    min_num: int = 1,
    max_num: int = 7,
    image_size: int = 448,
    use_thumbnail: bool = True,
) -> list[Image.Image]:
    if min_num < 1 or max_num < min_num:
        raise ValueError("InternVL tile limits must satisfy 1 <= min_num <= max_num")

    orig_width, orig_height = image.size
    if orig_width <= 0 or orig_height <= 0:
        raise ValueError(f"Invalid image dimensions: {image.size!r}")
    aspect_ratio = orig_width / orig_height
    target_ratios = sorted(
        {
            (width, height)
            for count in range(min_num, max_num + 1)
            for width in range(1, count + 1)
            for height in range(1, count + 1)
            if min_num <= width * height <= max_num
        },
        key=lambda ratio: ratio[0] * ratio[1],
    )
    target_ratio = find_closest_aspect_ratio(
        aspect_ratio,
        target_ratios,
        orig_width,
        orig_height,
        image_size,
    )
    target_width = image_size * target_ratio[0]
    target_height = image_size * target_ratio[1]
    blocks = target_ratio[0] * target_ratio[1]
    resized = image.resize((target_width, target_height), resample=Image.Resampling.BICUBIC)
    processed: list[Image.Image] = []
    columns = target_width // image_size
    for index in range(blocks):
        left = (index % columns) * image_size
        top = (index // columns) * image_size
        processed.append(resized.crop((left, top, left + image_size, top + image_size)))
    if use_thumbnail and len(processed) != 1:
        processed.append(
            image.resize((image_size, image_size), resample=Image.Resampling.BICUBIC)
        )
    return processed


def load_image(
    image_file: str | Path,
    input_size: int = 448,
    min_num: int = 1,
    max_num: int = 7,
    use_thumbnail: bool = True,
):
    import torch

    with Image.open(image_file) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    transform = build_transform(input_size)
    tiles = dynamic_preprocess(
        image,
        min_num=min_num,
        max_num=max_num,
        image_size=input_size,
        use_thumbnail=use_thumbnail,
    )
    return torch.stack([transform(tile) for tile in tiles])


class InternVL25Adapter:
    """Transformers remote-code backend for InternVL2.5 inference."""

    model_id = "OpenGVLab/InternVL2_5-8B"

    def __init__(
        self,
        model_id: str = model_id,
        revision: str | None = None,
        dtype: str = "bfloat16",
        device_map: str | dict[str, Any] | None = "auto",
        trust_remote_code: bool = True,
        use_flash_attn: bool = False,
        input_size: int = 448,
        min_num: int = 1,
        max_num: int = 7,
        use_thumbnail: bool = True,
    ) -> None:
        from transformers import AutoModel

        if trust_remote_code and not revision:
            raise ValueError(
                "InternVL remote code must use a pinned model revision for reproducibility"
            )
        self.dtype = _torch_dtype(dtype)
        self.model_id = model_id
        self.revision = revision
        self.input_size = input_size
        self.min_num = min_num
        self.max_num = max_num
        self.use_thumbnail = use_thumbnail
        self.use_flash_attn = use_flash_attn
        self.tokenizer = load_internvl_tokenizer(
            model_id,
            revision=revision,
            trust_remote_code=trust_remote_code,
        )
        self.model = AutoModel.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=self.dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=trust_remote_code,
            use_flash_attn=use_flash_attn,
            device_map=device_map,
        ).eval()
        ensure_generation_mixin(self.model)

    @staticmethod
    def build_question(input_row: dict[str, Any], prompt_profile: str) -> str:
        image_count = len(input_row["image_paths"])
        if image_count == 1:
            image_prefix = "<image>\n"
        else:
            image_prefix = "".join(
                f"Image-{index}: <image>\n" for index in range(1, image_count + 1)
            )
        return image_prefix + build_prompt_text(
            str(input_row["question_raw"]),
            prompt_profile,
        )

    def _prepare_images(self, image_paths: list[str]):
        import torch

        pixel_values_list = [
            load_image(
                path,
                input_size=self.input_size,
                min_num=self.min_num,
                max_num=self.max_num,
                use_thumbnail=self.use_thumbnail,
            )
            for path in image_paths
        ]
        num_patches_list = tuple(int(values.shape[0]) for values in pixel_values_list)
        pixel_values = torch.cat(pixel_values_list, dim=0)
        pixel_values = pixel_values.to(device=self.model.device, dtype=self.dtype)
        return pixel_values, num_patches_list

    def _build_model_inputs(
        self,
        input_row: dict[str, Any],
        prompt_profile: str,
        system_prompt: str | None,
        num_patches_list: tuple[int, ...],
    ):
        question = self.build_question(input_row, prompt_profile)
        template = deepcopy(self.model.conv_template)
        template.system_message = system_prompt or self.model.system_message
        template.append_message(template.roles[0], question)
        template.append_message(template.roles[1], None)
        rendered_prompt = template.get_prompt()

        image_context_token = "<IMG_CONTEXT>"
        self.model.img_context_token_id = self.tokenizer.convert_tokens_to_ids(
            image_context_token
        )
        expanded_prompt = rendered_prompt
        for num_patches in num_patches_list:
            image_tokens = (
                "<img>"
                + image_context_token * self.model.num_image_token * num_patches
                + "</img>"
            )
            if "<image>" not in expanded_prompt:
                raise ValueError("InternVL prompt has fewer image placeholders than inputs")
            expanded_prompt = expanded_prompt.replace("<image>", image_tokens, 1)
        if "<image>" in expanded_prompt:
            raise ValueError("InternVL prompt has more image placeholders than inputs")

        model_inputs = self.tokenizer(expanded_prompt, return_tensors="pt")
        input_ids = model_inputs["input_ids"].to(self.model.device)
        attention_mask = model_inputs["attention_mask"].to(self.model.device)
        eos_token_id = self.tokenizer.convert_tokens_to_ids(template.sep.strip())
        return rendered_prompt, input_ids, attention_mask, eos_token_id, template.sep.strip()

    def generate_one(
        self,
        input_row: dict[str, Any],
        prompt_profile: str,
        generation_config: dict[str, Any],
        system_prompt: str | None = None,
        score_labels: bool = False,
    ) -> InternVLGenerateOutput:
        import torch

        image_paths = [str(path) for path in input_row["image_paths"]]
        if not image_paths:
            raise ValueError("InternVL inference requires at least one image")
        pixel_values, num_patches_list = self._prepare_images(image_paths)
        (
            rendered_prompt,
            input_ids,
            attention_mask,
            eos_token_id,
            separator,
        ) = self._build_model_inputs(
            input_row,
            prompt_profile,
            system_prompt,
            num_patches_list,
        )
        generation_kwargs = _clean_kwargs(dict(generation_config))
        generation_kwargs["eos_token_id"] = eos_token_id
        if self.tokenizer.pad_token_id is not None:
            generation_kwargs.setdefault("pad_token_id", self.tokenizer.pad_token_id)
        if score_labels:
            generation_kwargs["return_dict_in_generate"] = True
            generation_kwargs["output_logits"] = True

        with torch.inference_mode():
            generation_output = self.model.generate(
                pixel_values=pixel_values,
                input_ids=input_ids,
                attention_mask=attention_mask,
                **generation_kwargs,
            )

        label_summary = None
        if score_labels:
            generated_ids = generation_output.sequences
            logits = getattr(generation_output, "logits", None)
            if logits is None or len(logits) == 0:
                raise RuntimeError("InternVL generation did not return first-step logits")
            label_summary = self._summarize_label_logits(logits[0][0], input_row)
        else:
            generated_ids = generation_output

        decoded = self.tokenizer.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        raw_output = decoded.split(separator, 1)[0].strip()
        visual_token_count = int(sum(num_patches_list) * self.model.num_image_token)
        return InternVLGenerateOutput(
            raw_output=raw_output,
            rendered_prompt=rendered_prompt,
            prompt_token_count=int(input_ids.shape[1]),
            output_token_count=int(generated_ids.shape[1]),
            label_summary=label_summary,
            num_patches_list=num_patches_list,
            visual_token_count=visual_token_count,
        )

    def _summarize_label_logits(
        self,
        next_token_logits: Any,
        input_row: dict[str, Any],
    ) -> LabelScoreSummary:
        import torch

        label_token_ids = self._label_token_ids()
        if any(len(ids) != 1 for ids in label_token_ids.values()):
            raise ValueError("A/B/C/D labels are not single-token under the InternVL tokenizer")
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
        return {
            label: list(self.tokenizer.encode(label, add_special_tokens=False))
            for label in LABELS
        }
