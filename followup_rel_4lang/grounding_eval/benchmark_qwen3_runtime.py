"""Profile one locked Qwen3-VL O/R/C GUI pair on a single GPU."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from run_qwen3_orc_element_pilot import CONDITIONS, _pairs
from run_qwen3_prompt_pilot import MODEL_ID, PROMPT, REPO, REVISION, _score


DEFAULT_PAIR = "rel::1/booking_10.jpg::zh::th"
DATA_ROOT = REPO / "followup_rel_4lang"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_locked_image(pair_id: str) -> Path:
    """Fetch only the selected screenshot after the checked bundle is unpacked."""
    manifest = json.loads((DATA_ROOT / "bundle_manifest.json").read_text(encoding="utf-8"))
    conditions = DATA_ROOT / "data/rel_all_366/conditions_4lang.jsonl"
    matching = []
    with conditions.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            candidate = f"{row['parallel_id']}::{row['query_language']}::{row['gui_language']}"
            if candidate == pair_id and row["condition"] == "O":
                matching.append(row)
    if len(matching) != 1:
        raise ValueError(f"Expected one locked O condition for {pair_id!r}; found {len(matching)}")
    relative = matching[0]["image_path"]
    entries = [row for row in manifest["images"] if row["path"] == relative]
    if len(entries) != 1 or not relative.startswith("assets/images/"):
        raise ValueError("Selected image is absent from the bundle manifest")
    entry = entries[0]
    target = (DATA_ROOT / relative).resolve()
    if not target.is_relative_to(DATA_ROOT.resolve()):
        raise ValueError("Image path escapes the data root")
    source = manifest["source"]
    expected_url = (
        f"https://huggingface.co/datasets/{source['hf_repo']}/resolve/"
        f"{source['hf_revision']}/"
        + quote(relative.removeprefix("assets/images/"), safe="/")
    )
    if entry["url"] != expected_url:
        raise ValueError("Image URL disagrees with the locked source")
    if target.exists():
        if target.stat().st_size != entry["bytes"] or _sha256(target) != entry["sha256"]:
            raise ValueError(f"Existing image differs from the locked source: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".download")
    with urlopen(expected_url, timeout=60) as response, temporary.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    if temporary.stat().st_size != entry["bytes"] or _sha256(temporary) != entry["sha256"]:
        temporary.unlink()
        raise ValueError("Downloaded image checksum mismatch")
    temporary.replace(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True,
                        help="Pinned Hugging Face snapshot directory returned by hf download")
    parser.add_argument("--pair-id", default=DEFAULT_PAIR)
    parser.add_argument("--max-pixels", type=int, choices=(1048576, 2097152), default=2097152)
    parser.add_argument("--batch-size", type=int, choices=(1, 3), default=3)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--output", type=Path, help="Fresh JSON path for measured results")
    args = parser.parse_args()
    if not args.preflight_only and args.output is None:
        parser.error("--output is required for GPU measurement")
    if args.output is not None and args.output.exists():
        parser.error(f"Output already exists: {args.output}")

    snapshot = args.model_path.resolve()
    if snapshot.name != REVISION or not (snapshot / "config.json").is_file():
        parser.error(f"--model-path must be the pinned {MODEL_ID} snapshot {REVISION}")
    config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "qwen3_vl":
        parser.error("--model-path is not a Qwen3-VL checkpoint")

    os.environ.setdefault("OMP_NUM_THREADS", "3")
    os.environ.setdefault("MKL_NUM_THREADS", "3")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "3")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    import transformers
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    image = _ensure_locked_image(args.pair_id)
    pair = _pairs(only_pair_id=args.pair_id)[0]
    assert image == pair["image_path"].resolve()
    conditions = CONDITIONS if args.batch_size == 3 else CONDITIONS[:1]
    processor = AutoProcessor.from_pretrained(
        snapshot, local_files_only=True, min_pixels=262144, max_pixels=args.max_pixels,
    )
    processor.tokenizer.padding_side = "left"
    assert int(processor.image_processor.patch_size) == 16

    started = time.perf_counter()
    conversations = [[{"role": "user", "content": [
        {"type": "image", "image": image.as_posix()},
        {"type": "text", "text": PROMPT.format(text=pair["descriptors"][condition])},
    ]}] for condition in conditions]
    rendered = [processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                for messages in conversations]
    images, videos = process_vision_info(conversations, image_patch_size=16)
    inputs = processor(text=rendered, images=images, videos=videos,
                       padding=True, return_tensors="pt")
    grids = inputs["image_grid_thw"].tolist()
    assert len(grids) == args.batch_size and len({tuple(grid) for grid in grids}) == 1
    prompt_tokens = inputs.attention_mask.sum(dim=1).tolist()
    preprocess_s = time.perf_counter() - started
    common = {
        "schema": "qwen3-vl-runtime-probe-v1", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID, "revision": REVISION, "pair_id": args.pair_id,
        "image_sha256": pair["image_sha256"], "image_grid_thw": grids[0],
        "visual_tokens_per_image": grids[0][0] * grids[0][1] * grids[0][2] // 4,
        "conditions": list(conditions), "batch_size": args.batch_size,
        "min_pixels": 262144, "max_pixels": args.max_pixels,
        "prompt_tokens": prompt_tokens, "preprocess_s": round(preprocess_s, 3),
        "dtype": "bfloat16", "attn_implementation": "sdpa",
        "torch_version": torch.__version__, "transformers_version": transformers.__version__,
    }
    if args.preflight_only:
        print(json.dumps({**common, "preflight_only": True}, ensure_ascii=False, indent=2))
        return

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU unavailable")
    torch.set_num_threads(3)
    load_start = time.perf_counter()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        snapshot, local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": "cuda:0"}, low_cpu_mem_usage=True,
    )
    load_s = time.perf_counter() - load_start
    assert all(parameter.device.type == "cuda" for parameter in model.parameters())
    assert model.config._attn_implementation == "sdpa"
    model.eval()
    inputs = inputs.to(model.device)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    times: dict[str, list[float]] = defaultdict(list)
    starts: dict[str, list[float]] = defaultdict(list)
    hooks = []

    def add_timing(module, name: str) -> None:
        def before(_module, _args):
            torch.cuda.synchronize()
            starts[name].append(time.perf_counter())

        def after(_module, _args, _output):
            torch.cuda.synchronize()
            times[name].append(time.perf_counter() - starts[name].pop())

        hooks.extend((module.register_forward_pre_hook(before), module.register_forward_hook(after)))

    add_timing(model, "whole_forward")
    add_timing(model.model.visual, "vision_forward")
    add_timing(model.model.language_model, "language_forward")
    generate_start = time.perf_counter()
    try:
        with torch.inference_mode():
            generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
    finally:
        for hook in hooks:
            hook.remove()
    torch.cuda.synchronize()
    generate_s = time.perf_counter() - generate_start
    eos = model.generation_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    rows = []
    for index, condition in enumerate(conditions):
        suffix = generated[index, inputs.input_ids.shape[1]:].detach().cpu().tolist()
        stop = next((i for i, token in enumerate(suffix) if token in eos_ids), None)
        tokens = suffix[:stop + 1] if stop is not None else suffix
        raw = processor.decode(tokens, skip_special_tokens=True,
                               clean_up_tokenization_spaces=False).strip()
        rows.append({"condition": condition, "raw_output": raw, "output_tokens": len(tokens),
                     "stop_reason": "eos" if stop is not None else "length", **_score(raw, pair)})
    result = {
        **common, "gpu": torch.cuda.get_device_name(0), "model_load_s": round(load_s, 3),
        "generate_s": round(generate_s, 3),
        "prefill_forward_s": round(times["whole_forward"][0], 3),
        "decode_forward_s": round(sum(times["whole_forward"][1:]), 3),
        "vision_forward_s": round(sum(times["vision_forward"]), 3),
        "language_prefill_s": round(times["language_forward"][0], 3),
        "language_decode_s": round(sum(times["language_forward"][1:]), 3),
        "forward_calls": len(times["whole_forward"]),
        "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 3),
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
