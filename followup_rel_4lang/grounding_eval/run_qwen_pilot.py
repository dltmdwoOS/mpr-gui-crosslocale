"""Run only the locked Qwen grounding controls and pilot, with resumable records.

The pinned 7B checkpoint is streamed one shard at a time into a disposable file.
This keeps peak disk use below one shard on the shared laboratory filesystem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image

if __package__:
    from .build_protocol_inputs import HERE, REPO, render_qwen_user_prompt
    from .point_format import qwen_image_size_from_grid, score_qwen_point
else:
    from build_protocol_inputs import HERE, REPO, render_qwen_user_prompt
    from point_format import qwen_image_size_from_grid, score_qwen_point


MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
REVISION = "cc594898137f460bfe9f0759e9844b3ce807cfb5"
PERSONAL_CACHE = Path("/home/jovyan/seungjae/.cache")
INPUT_DIR = REPO / "followup_rel_4lang/results/grounding_protocol_inputs_v3"
DEFAULT_OUTPUT = REPO / "followup_rel_4lang/results/grounding_pilot_qwen_v3"
PHRASE_OUTPUT = REPO / "followup_rel_4lang/results/grounding_pilot_qwen_phrase_v1"
PHRASE_FILE = HERE / "pilot_referent_phrases.json"
MODEL_CONFIG = REPO / "01_code/configs/models/qwen2_5_vl_7b.yaml"
GT_PATH = HERE / "annotations_20261103/grounding_gt_draft_170.json"
SHARD_RE = re.compile(r"model-[0-9]{5}-of-[0-9]{5}\.safetensors\Z")
MIN_FREE_AFTER_DOWNLOAD = 8 * 2**30


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_inputs() -> tuple[list[dict], list[dict], str]:
    tracked = (HERE / "input_lock.json").read_bytes()
    assert (INPUT_DIR / "input_lock.json").read_bytes() == tracked
    lock = json.loads(tracked)
    assert lock["schema"] == "rel-grounding-protocol-inputs-v3"
    for name, expected in lock["generated_sha256"].items():
        assert _sha256(INPUT_DIR / name) == expected, name
    controls = _read_jsonl(INPUT_DIR / "positive_controls.jsonl")
    pilot = [row for row in _read_jsonl(INPUT_DIR / "grounding_pairs.jsonl")
             if row["split"] == "pilot"]
    assert len(controls) == 8 and len(pilot) == 48
    assert len({row["pair_id"] for row in pilot}) == 48
    return controls, pilot, hashlib.sha256(tracked).hexdigest()


def _load_phrase_descriptors(controls: list[dict], pilot: list[dict]) -> tuple[dict, str, str]:
    content = PHRASE_FILE.read_bytes()
    package = json.loads(content)
    assert package["schema"] == "rel-grounding-pilot-referent-phrases-v1"
    descriptors = package["descriptors"]
    assert set(descriptors) == {row["parallel_id"] for row in pilot}
    assert all(set(locales) == {"en", "zh", "th", "ru"} for locales in descriptors.values())
    for row in pilot:
        _phrase_from_question(row["question_O"], descriptors[row["parallel_id"]][row["query_language"]],
                              require_substring=True)
        _phrase_from_question(row["question_R"], descriptors[row["parallel_id"]][row["query_language"]],
                              require_substring=True)
    for row in controls:
        _phrase_from_question(row["question"], descriptors[row["parallel_id"]][row["gui_language"]],
                              require_substring=True)
    template = package["prompt_template"]
    assert "{descriptor}" in template and "{model_width}" in template and "{model_height}" in template
    return descriptors, template, hashlib.sha256(content).hexdigest()


def _phrase_from_question(question: str, template: str, require_substring: bool = False) -> str:
    match = re.search(r"<ref>[^<>]+</ref>", question)
    assert match and question.count("<ref>") == question.count("</ref>") == 1
    assert template.count("{ref}") == 1
    phrase = template.format(ref=match.group(0))
    if require_substring:
        assert phrase in question
    return phrase


def _trials(controls: list[dict], pilot: list[dict], descriptors: dict | None = None) -> tuple[list[dict], list[dict]]:
    control_trials = [
        {"trial_id": f"control::{row['parallel_id']}::{row['gui_language']}",
         "phase": "control", "condition": "same", "row": row,
         "marked_stem": _phrase_from_question(
             row["question"], descriptors[row["parallel_id"]][row["gui_language"]])
         if descriptors is not None else row["question"]}
        for row in controls
    ]
    pilot_trials = []
    for row in pilot:
        parity = hashlib.sha256(row["pair_id"].encode("utf-8")).digest()[0] % 2
        order = ("O", "R") if parity == 0 else ("R", "O")
        for condition in order:
            pilot_trials.append({
                "trial_id": f"pilot::{row['pair_id']}::{condition}",
                "phase": "pilot", "condition": condition, "row": row,
                "marked_stem": _phrase_from_question(
                    row[f"question_{condition}"], descriptors[row["parallel_id"]][row["query_language"]])
                if descriptors is not None else row[f"question_{condition}"],
            })
    assert len(control_trials) == 8 and len(pilot_trials) == 96
    assert len({trial["trial_id"] for trial in control_trials + pilot_trials}) == 104
    return control_trials, pilot_trials


def _load_processor():
    from transformers import AutoProcessor
    import yaml

    config = yaml.safe_load(MODEL_CONFIG.read_text(encoding="utf-8"))
    assert config["model_id"] == MODEL_ID and config["revision"] == REVISION
    assert config["model_family"] == "qwen2_5_vl"
    min_pixels, max_pixels = config["min_pixels"], config["max_pixels"]
    snapshot = PERSONAL_CACHE / "huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots" / REVISION
    processor = AutoProcessor.from_pretrained(
        snapshot, local_files_only=True, min_pixels=min_pixels, max_pixels=max_pixels,
    )
    processor.tokenizer.padding_side = "left"
    return processor, snapshot, min_pixels, max_pixels


def _preflight_image(processor, image_path: Path, expected_hash: str, expected_size: list[int]) -> dict:
    from qwen_vl_utils import process_vision_info

    assert image_path.is_file() and _sha256(image_path) == expected_hash, image_path
    with Image.open(image_path) as image:
        original_size = image.size
    assert list(original_size) == expected_size, image_path
    user = {"role": "user", "content": [
        {"type": "image", "image": image_path.as_posix()},
        {"type": "text", "text": "Locate one reference element."},
    ]}
    probe = processor.apply_chat_template([user], tokenize=False, add_generation_prompt=True)
    images, videos = process_vision_info([user])
    assert len(images) == 1 and not videos
    inputs = processor(text=[probe], images=images, videos=videos, return_tensors="pt")
    grid = inputs["image_grid_thw"][0].tolist()
    width, height = qwen_image_size_from_grid(grid)
    return {"grid": grid, "model_width": width, "model_height": height,
            "intermediate_size": list(images[0].size), "original_size": list(original_size)}


def _checkpoint_name(name: str) -> str:
    if name.startswith("visual."):
        return "model.visual." + name[len("visual."):]
    if name.startswith("model."):
        return "model.language_model." + name[len("model."):]
    return name


def _stream_shard(path: Path, filename: str) -> None:
    import requests
    from huggingface_hub import get_hf_file_metadata, hf_hub_url

    url = hf_hub_url(MODEL_ID, filename, revision=REVISION)
    metadata = get_hf_file_metadata(url, token=False)
    etag = metadata.etag.strip('"')
    assert metadata.size and re.fullmatch(r"[0-9a-f]{64}", etag)
    if shutil.disk_usage(PERSONAL_CACHE).free < metadata.size + MIN_FREE_AFTER_DOWNLOAD:
        raise RuntimeError(f"Insufficient shared-disk reserve for {filename}")
    try:
        response = requests.get(metadata.location, stream=True, timeout=(30, 120))
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        digest = hashlib.sha256()
        length = 0
        with path.open("wb") as handle:
            for block in response.iter_content(chunk_size=8 * 1024 * 1024):
                if block:
                    handle.write(block)
                    digest.update(block)
                    length += len(block)
        if length != metadata.size or digest.hexdigest() != etag:
            raise RuntimeError("size or SHA-256 mismatch")
    except Exception as exc:
        # Signed redirect URLs can contain credentials; never print the exception.
        raise RuntimeError(f"Could not verify download of {filename}: {type(exc).__name__}") from None
    finally:
        if "response" in locals():
            response.close()


def _load_model_streamed(snapshot: Path):
    import torch
    from accelerate import init_empty_weights
    from accelerate.utils import set_module_tensor_to_device
    from safetensors import safe_open
    from transformers import AutoConfig, GenerationConfig, Qwen2_5_VLForConditionalGeneration

    assert torch.cuda.is_available(), "Qwen pilot requires the assigned GPU"
    index = json.loads((snapshot / "model.safetensors.index.json").read_text(encoding="utf-8"))["weight_map"]
    shards = sorted(set(index.values()))
    assert len(shards) == 5 and all(SHARD_RE.fullmatch(name) for name in shards)
    config = AutoConfig.from_pretrained(snapshot, local_files_only=True)
    config._attn_implementation = "sdpa"
    with init_empty_weights():
        model = Qwen2_5_VLForConditionalGeneration(config)
    assert {_checkpoint_name(name) for name in index} == set(model.state_dict())
    model.generation_config = GenerationConfig.from_pretrained(snapshot, local_files_only=True)

    temp_root = PERSONAL_CACHE / "qwen_grounding_pilot_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    for number, shard in enumerate(shards, 1):
        print(f"Loading pinned checkpoint shard {number}/{len(shards)}", flush=True)
        with tempfile.TemporaryDirectory(prefix="shard_", dir=temp_root) as temp_dir:
            path = Path(temp_dir) / shard
            _stream_shard(path, shard)
            expected = {key for key, filename in index.items() if filename == shard}
            with safe_open(path, framework="pt", device="cpu") as handle:
                assert set(handle.keys()) == expected, shard
                for key in handle.keys():
                    tensor = handle.get_tensor(key)
                    set_module_tensor_to_device(
                        model, _checkpoint_name(key), "cuda:0", value=tensor,
                        dtype=torch.bfloat16,
                    )
                    del tensor
    assert not any(parameter.is_meta for parameter in model.parameters())
    model.to("cuda:0")  # Move the small non-persistent rotary buffers too.
    model.eval()
    return model


def _generate_one(model, processor, trial: dict, image_info: dict, gt: dict,
                  lock_hash: str, min_pixels: int, max_pixels: int,
                  phrase_prompt_template: str | None = None, descriptor_hash: str | None = None) -> dict:
    import torch
    from qwen_vl_utils import process_vision_info

    row = trial["row"]
    image_path = REPO / row["image_path"]
    if phrase_prompt_template is None:
        user_prompt = render_qwen_user_prompt(
            trial["marked_stem"], image_info["model_width"], image_info["model_height"],
        )
    else:
        user_prompt = phrase_prompt_template.format(
            descriptor=trial["marked_stem"], model_width=image_info["model_width"],
            model_height=image_info["model_height"],
        )
    messages = [
        {"role": "user", "content": [
            {"type": "image", "image": image_path.as_posix()},
            {"type": "text", "text": user_prompt},
        ]},
    ]
    rendered_prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    images, videos = process_vision_info(messages)
    inputs = processor(text=[rendered_prompt], images=images, videos=videos, return_tensors="pt")
    actual_grid = inputs["image_grid_thw"][0].tolist()
    assert actual_grid == image_info["grid"], trial["trial_id"]
    assert list(images[0].size) == image_info["intermediate_size"]
    inputs = inputs.to(model.device)
    with torch.inference_mode():
        generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
    raw = processor.batch_decode(
        generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()
    annotation = gt[row["parallel_id"]][row["gui_language"]]
    score = score_qwen_point(raw, annotation["bbox"], *annotation["image_size"],
                             image_info["model_width"], image_info["model_height"])
    return {
        "trial_id": trial["trial_id"], "phase": trial["phase"],
        "pair_id": row.get("pair_id"), "parallel_id": row["parallel_id"],
        "condition": trial["condition"], "query_language": row.get("query_language", row["gui_language"]),
        "gui_language": row["gui_language"], "image_path": row["image_path"],
        "image_sha256": row["image_sha256"], "input_lock_sha256": lock_hash,
        "descriptor_sha256": descriptor_hash,
        "model_id": MODEL_ID, "revision": REVISION,
        "min_pixels": min_pixels, "max_pixels": max_pixels,
        "image_grid_thw": actual_grid, "intermediate_image_size": image_info["intermediate_size"],
        "original_image_size": image_info["original_size"], "rendered_prompt": rendered_prompt,
        "raw_output": raw, "output_tokens": int(generated.shape[1] - inputs.input_ids.shape[1]),
        **score,
    }


def _existing(path: Path, expected: set[str], lock_hash: str,
              descriptor_hash: str | None = None) -> dict[str, dict]:
    if not path.exists():
        return {}
    records = _read_jsonl(path)
    by_id = {record["trial_id"]: record for record in records}
    assert len(by_id) == len(records) and set(by_id) <= expected
    assert all(record["input_lock_sha256"] == lock_hash and record["revision"] == REVISION and
               record.get("descriptor_sha256") == descriptor_hash
               for record in records)
    return by_id


def _summary(controls: dict[str, dict], pilot: dict[str, dict], phrase_diagnostic: bool = False) -> dict:
    control_rows = list(controls.values())
    pilot_rows = list(pilot.values())
    control_valid = sum(row["valid_output"] for row in control_rows)
    control_hit = sum(row["point_in_gt_box"] for row in control_rows)
    gate = len(control_rows) == 8 and control_valid == 8 and control_hit >= 6
    pairs: dict[str, dict] = {}
    for row in pilot_rows:
        pairs.setdefault(row["pair_id"], {})[row["condition"]] = row
    complete = [value for value in pairs.values() if set(value) == {"O", "R"}]
    transitions = {f"{o}->{r}": sum(
        int(value["O"]["point_in_gt_box"]) == o and
        int(value["R"]["point_in_gt_box"]) == r for value in complete)
        for o in (0, 1) for r in (0, 1)}
    return {
        "schema": "rel-grounding-qwen-phrase-pilot-v1" if phrase_diagnostic else "rel-grounding-qwen-pilot-v3",
        "control_count": len(control_rows),
        "control_valid": control_valid, "control_format_adherent": sum(
            row["requested_format_adherent"] for row in control_rows),
        "control_hit": control_hit, "control_gate_passed": gate,
        "pilot_count": len(pilot_rows), "pilot_valid": sum(row["valid_output"] for row in pilot_rows),
        "pilot_format_adherent": sum(row["requested_format_adherent"] for row in pilot_rows),
        "pilot_hit_O": sum(row["point_in_gt_box"] for row in pilot_rows if row["condition"] == "O"),
        "pilot_hit_R": sum(row["point_in_gt_box"] for row in pilot_rows if row["condition"] == "R"),
        "pilot_complete_pairs": len(complete), "pilot_transitions": transitions,
        "pilot_format_gate_passed": len(pilot_rows) == 96 and
                                    sum(row["valid_output"] for row in pilot_rows) >= 90,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true", help="Check locked pilot images on CPU")
    parser.add_argument("--phrase-diagnostic", action="store_true",
                        help="Use pilot-only referring phrases; run exploratory O/R even if control gate fails")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    os.environ["XDG_CACHE_HOME"] = str(PERSONAL_CACHE)
    os.environ["HF_HOME"] = str(PERSONAL_CACHE / "huggingface")
    os.environ["TORCH_HOME"] = str(PERSONAL_CACHE / "torch")
    os.environ["PIP_CACHE_DIR"] = str(PERSONAL_CACHE / "pip")
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = "3"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    # The existing server setup enables offline cache reuse for normal runs;
    # temporary shard streaming needs network access without filling that cache.
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    controls, pilot, lock_hash = _load_inputs()
    descriptors, phrase_template, descriptor_hash = (None, None, None)
    if args.phrase_diagnostic:
        descriptors, phrase_template, descriptor_hash = _load_phrase_descriptors(controls, pilot)
    control_trials, pilot_trials = _trials(controls, pilot, descriptors)
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))["annotations"]
    processor, snapshot, min_pixels, max_pixels = _load_processor()
    image_info = {}
    for trial in control_trials + pilot_trials:
        row = trial["row"]
        path = REPO / row["image_path"]
        if path not in image_info:
            annotation = gt[row["parallel_id"]][row["gui_language"]]
            assert annotation["image_sha256"] == row["image_sha256"]
            image_info[path] = _preflight_image(
                processor, path, row["image_sha256"], annotation["image_size"],
            )
    print(json.dumps({"locked_control_trials": len(control_trials),
                      "locked_pilot_trials": len(pilot_trials),
                      "unique_images_preflighted": len(image_info),
                      "input_lock_sha256": lock_hash,
                      "descriptor_sha256": descriptor_hash}, indent=2), flush=True)
    if args.preflight_only:
        return

    output = (args.output_dir or (PHRASE_OUTPUT if args.phrase_diagnostic else DEFAULT_OUTPUT)).resolve()
    output.mkdir(parents=True, exist_ok=True)
    control_path, pilot_path = output / "controls.jsonl", output / "pilot.jsonl"
    existing_controls = _existing(control_path, {trial["trial_id"] for trial in control_trials},
                                  lock_hash, descriptor_hash)
    existing_pilot = _existing(pilot_path, {trial["trial_id"] for trial in pilot_trials},
                               lock_hash, descriptor_hash)
    model = _load_model_streamed(snapshot)

    for trial in control_trials:
        if trial["trial_id"] in existing_controls:
            continue
        record = _generate_one(model, processor, trial, image_info[REPO / trial["row"]["image_path"]],
                               gt, lock_hash, min_pixels, max_pixels, phrase_template, descriptor_hash)
        with control_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing_controls[trial["trial_id"]] = record
        print(f"Control {len(existing_controls)}/8: valid={record['valid_output']} hit={record['point_in_gt_box']}", flush=True)
    current = _summary(existing_controls, existing_pilot, args.phrase_diagnostic)
    (output / "summary.json").write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not current["control_gate_passed"]:
        if not args.phrase_diagnostic:
            print("Control gate failed; pilot generation was not started.", flush=True)
            return
        print("Control gate failed; continuing pilot only as an exploratory diagnostic.", flush=True)

    for trial in pilot_trials:
        if trial["trial_id"] in existing_pilot:
            continue
        record = _generate_one(model, processor, trial, image_info[REPO / trial["row"]["image_path"]],
                               gt, lock_hash, min_pixels, max_pixels, phrase_template, descriptor_hash)
        with pilot_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing_pilot[trial["trial_id"]] = record
        if len(existing_pilot) % 8 == 0:
            print(f"Pilot {len(existing_pilot)}/96", flush=True)
    final = _summary(existing_controls, existing_pilot, args.phrase_diagnostic)
    (output / "summary.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
