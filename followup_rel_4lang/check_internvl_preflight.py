"""InternVL qualification check on one RTX 4090 before any full run (batch size 1).

Runs the longest question of each 6x6 dimension and the longest grounding pilot
trial once, and records time, peak memory, visual tokens and output form. It
stops with a non-zero exit if a multiple-choice output is not a single A-D label,
if label tokens are not single tokens, if the explicit English system prompt is
not in the rendered prompt, or if visual tokens exceed the configured cap.
It is a functionality check, not a guarantee for every full-dataset input.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "01_code/src"))
sys.path.insert(0, str(REPO / "followup_rel_4lang/grounding_eval"))
from mpr_crosslocale.data.cross_locale_sampling import build_cross_locale_plan, build_language_pairs  # noqa: E402
from mpr_crosslocale.inference.answer_parser import parse_label  # noqa: E402
from mpr_crosslocale.inference.run_cross_locale import INTERNVL_FAMILIES, _build_model_adapter  # noqa: E402
from mpr_crosslocale.inference.runtime import load_yaml, read_jsonl, resolve_paths, software_versions  # noqa: E402
from mpr_crosslocale.inference.system_prompts import build_system_prompt  # noqa: E402
from run_internvl_grounding import GENERATION as GROUNDING_GENERATION, SYSTEM_MESSAGE  # noqa: E402
from run_qwen3_grounding import build_groups  # noqa: E402
from run_qwen3_prompt_pilot import PROMPT, _score  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh output path; do not overwrite a preflight record")
    config = load_yaml(args.model_config)
    if config.get("model_family") not in INTERNVL_FAMILIES:
        parser.error("Use a pinned InternVL configuration")
    manifest = read_jsonl(args.manifest)
    plan = build_cross_locale_plan(manifest, build_language_pairs(None, None),
                                   {"wf", "wi", "au", "ap", "ael", "rel"}, None, "semantic_items", 42)
    rows = resolve_paths(plan.rows, REPO / "01_code")
    trials = [t for g in build_groups("pilot") for t in g["trials"]]
    record = {
        "config_sha256": hashlib.sha256(args.model_config.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "model_id": config["model_id"], "revision": config["revision"], "batch_size": 1,
        "cross_locale_inputs": len(rows), "software": software_versions(),
    }
    if args.plan_only:
        print(json.dumps(record, indent=2))
        return

    import torch

    torch.set_num_threads(3)
    if torch.cuda.device_count() != 1 or "4090" not in torch.cuda.get_device_name(0):
        raise RuntimeError("Expose exactly one RTX 4090 with CUDA_VISIBLE_DEVICES")
    record["gpu"] = torch.cuda.get_device_name(0)
    adapter = _build_model_adapter(SimpleNamespace(attn_implementation=None, device_map="cuda:0"), config)
    tokenizer = adapter.tokenizer
    label_ids = adapter._label_token_ids()
    record["label_token_ids"] = label_ids
    problems = []
    language_model = adapter.model.language_model
    measured_attention = getattr(language_model.config, "_attn_implementation", None)
    record["measured_runtime"] = {
        "language_model_class": type(language_model).__name__,
        "language_model_attn_implementation": measured_attention,
        "vision_use_flash_attn": getattr(adapter.model.vision_model.config, "use_flash_attn", None),
        "num_image_token": int(adapter.model.num_image_token),
    }
    expected_attention = config.get("attn_implementation", "eager")
    if measured_attention != expected_attention:
        problems.append(f"language model attention is {measured_attention!r}, config says {expected_attention!r}")
    if int(adapter.model.num_image_token) != 256:
        problems.append(f"num_image_token is {adapter.model.num_image_token}, expected 256")
    if any(len(ids) != 1 for ids in label_ids.values()):
        problems.append("A-D labels are not single tokens")

    cases = []
    for dimension in ("wf", "wi", "au", "ap", "ael", "rel"):
        candidates = [r for r in rows if r["dimension"] == dimension]
        longest = max({r["question_raw"]: r for r in candidates}.values(),
                      key=lambda r: len(tokenizer.encode(r["question_raw"])))
        largest = max(candidates, key=lambda r: len(r["image_paths"]))
        cases.append((dimension, {**longest, "image_paths": largest["image_paths"]}))
    ground = max(trials, key=lambda r: len(tokenizer.encode(PROMPT.format(text=r["marked_text"]))))

    cap = int(config.get("vision_token_limit", 2048))
    measurements = []
    for name, row in cases:
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        system_prompt = build_system_prompt("english_fixed", row["question_language"])[0]
        started = time.perf_counter()
        output = adapter.generate_one(row, config["prompt_profile"], config["generation"],
                                      system_prompt=system_prompt, score_labels=True)
        torch.cuda.synchronize()
        label = parse_label(output.raw_output)
        scored = output.label_summary.scored_predicted_label if output.label_summary else None
        per_image_cap = cap * len(row["image_paths"])
        if label is None:
            problems.append(f"{name}: output is not a single A-D label: {output.raw_output!r}")
        if not output.rendered_prompt.startswith("<|im_start|>system\n" + system_prompt):
            problems.append(f"{name}: explicit English system prompt missing")
        if output.visual_token_count and output.visual_token_count > per_image_cap:
            problems.append(f"{name}: visual tokens {output.visual_token_count} > {per_image_cap}")
        measurements.append({
            "case": name, "input_id": row["input_id"], "images": len(row["image_paths"]),
            "seconds": time.perf_counter() - started,
            "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
            "prompt_tokens": output.prompt_token_count, "visual_tokens": output.visual_token_count,
            "num_patches": list(output.num_patches_list), "raw_output": output.raw_output,
            "generated_label": label, "scored_label": scored,
        })
        print(f"case={name} {measurements[-1]['seconds']:.2f}s "
              f"{measurements[-1]['peak_reserved_gib']:.2f}GiB raw={output.raw_output!r}", flush=True)

    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    image = REPO / "followup_rel_4lang" / ground["image_path"]
    started = time.perf_counter()
    result = adapter.generate_freeform([image.as_posix()], PROMPT.format(text=ground["marked_text"]),
                                       GROUNDING_GENERATION, SYSTEM_MESSAGE)
    torch.cuda.synchronize()
    measurements.append({
        "case": "grounding", "trial_id": ground["trial_id"],
        "seconds": time.perf_counter() - started,
        "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
        "prompt_tokens": result["prompt_tokens"], "visual_tokens": result["visual_token_count"],
        "raw_output": result["raw_output"], "valid_point": _score(result["raw_output"], ground)["valid_output"],
    })
    print(f"case=grounding raw={result['raw_output']!r}", flush=True)

    record.update(measurements=measurements, problems=problems,
                  status="passed" if not problems else "failed",
                  note="Functionality check at batch 1; not a guarantee for every input.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if problems:
        raise SystemExit("Preflight failed:\n- " + "\n- ".join(problems))
    print("Preflight passed", flush=True)


if __name__ == "__main__":
    main()
