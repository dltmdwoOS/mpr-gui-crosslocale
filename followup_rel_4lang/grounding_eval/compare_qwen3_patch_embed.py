"""Compare native and channels-last Conv3D on all patches of one locked image."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

if __package__:
    from .benchmark_qwen3_runtime import DEFAULT_PAIR, _ensure_locked_image
    from .run_qwen3_prompt_pilot import REVISION
else:
    from benchmark_qwen3_runtime import DEFAULT_PAIR, _ensure_locked_image
    from run_qwen3_prompt_pilot import REVISION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.model_path.name != REVISION:
        parser.error("Use a fresh output and the pinned model snapshot")
    import torch
    from qwen_vl_utils import process_vision_info
    from safetensors import safe_open
    from transformers import AutoConfig, AutoProcessor
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLVisionPatchEmbed

    torch.set_num_threads(3)
    config = AutoConfig.from_pretrained(args.model_path, local_files_only=True)
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True,
                                             min_pixels=262144, max_pixels=2097152)
    image = _ensure_locked_image(DEFAULT_PAIR)
    images, _ = process_vision_info([{"role": "user", "content": [
        {"type": "image", "image": image.as_posix()},
    ]}], image_patch_size=16)
    inputs = processor.image_processor(images=images, return_tensors="pt")
    pixels = inputs["pixel_values"].to(device="cuda", dtype=torch.bfloat16)
    module = Qwen3VLVisionPatchEmbed(config.vision_config).to(device="cuda", dtype=torch.bfloat16).eval()
    index = json.loads((args.model_path / "model.safetensors.index.json").read_text())["weight_map"]
    state = {}
    for field in ("weight", "bias"):
        key = next(k for k in index if k.endswith(f"visual.patch_embed.proj.{field}"))
        with safe_open(args.model_path / index[key], framework="pt", device="cpu") as handle:
            state[f"proj.{field}"] = handle.get_tensor(key)
    module.load_state_dict(state)
    weight_before = module.proj.weight.detach().clone()
    x = pixels.view(-1, module.in_channels, module.temporal_patch_size,
                    module.patch_size, module.patch_size)

    def backend():
        return str(torch._C._select_conv_backend(x, module.proj.weight, module.proj.bias,
                                                 list(module.proj.stride), [0, 0, 0], [1, 1, 1],
                                                 False, [0, 0, 0], 1))

    native_backend = backend()
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        native = module(pixels)
    torch.cuda.synchronize()
    native_s = time.perf_counter() - started
    module.proj.to(memory_format=torch.channels_last_3d)
    optimized_backend = backend()
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        optimized = module(pixels)
    torch.cuda.synchronize()
    optimized_s = time.perf_counter() - started
    delta = (native.float() - optimized.float()).abs()
    result = {
        "schema": "qwen3-patch-embed-layout-comparison-v1", "revision": REVISION,
        "torch_version": torch.__version__, "gpu": torch.cuda.get_device_name(0),
        "dtype": "bfloat16", "pixel_values_shape": list(pixels.shape),
        "image_grid_thw": inputs["image_grid_thw"].tolist(),
        "native_backend": native_backend, "channels_last_backend": optimized_backend,
        "native_s": native_s, "channels_last_s": optimized_s,
        "weight_values_identical": torch.equal(weight_before, module.proj.weight),
        "outputs_bitwise_identical": torch.equal(native, optimized),
        "output_elements": native.numel(), "different_elements": int(torch.count_nonzero(delta).item()),
        "max_abs_error": delta.max().item(), "mean_abs_error": delta.mean().item(),
        "allclose_rtol_1e_2_atol_1e_2": torch.allclose(native.float(), optimized.float(), rtol=0.01, atol=0.01),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
