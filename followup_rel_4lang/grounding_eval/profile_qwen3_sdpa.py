"""Run the locked benchmark and trace its first real SDPA call.

All arguments except --profile-output and --sdpa-backend are passed unchanged
to benchmark_qwen3_runtime.py. Profiling overhead is included in its timings.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--profile-output", type=Path, required=True)
    parser.add_argument("--sdpa-backend", choices=("auto", "flash", "efficient", "math", "cudnn"),
                        default="auto")
    args, remaining = parser.parse_known_args()
    if args.profile_output.exists():
        parser.error("Profile output already exists")
    import torch
    from torch.nn import functional
    from torch.nn.attention import SDPBackend, sdpa_kernel

    if __package__:
        from .benchmark_qwen3_runtime import main as benchmark
    else:
        from benchmark_qwen3_runtime import main as benchmark
    original = functional.scaled_dot_product_attention
    captured = []

    def traced(query, key, value, *positional, **kwargs):
        if captured:
            return original(query, key, value, *positional, **kwargs)
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,
                                               torch.profiler.ProfilerActivity.CUDA]) as profile:
            result = original(query, key, value, *positional, **kwargs)
            torch.cuda.synchronize()
        events = [{"name": e.key, "calls": e.count, "cpu_time_total_us": e.cpu_time_total,
                   "device_time_total_us": e.device_time_total}
                  for e in profile.key_averages()]
        record = {
            "schema": "qwen3-first-real-sdpa-v1", "backend_policy": args.sdpa_backend,
            "query_shape": list(query.shape), "key_shape": list(key.shape),
            "value_shape": list(value.shape), "query_stride": list(query.stride()),
            "dtype": str(query.dtype), "device": str(query.device),
            "is_causal": kwargs.get("is_causal"), "enable_gqa": kwargs.get("enable_gqa"),
            "events": events, "timing_includes_profiler_overhead": True,
            "synchronized_wall_s": time.perf_counter() - started,
        }
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output.write_text(json.dumps(record, indent=2) + "\n")
        captured.append(record)
        print(json.dumps({"first_sdpa_shape": list(query.shape),
                          "attention_events": [e for e in events if "attention" in e["name"]]}),
              flush=True)
        return result

    backends = {"flash": SDPBackend.FLASH_ATTENTION, "efficient": SDPBackend.EFFICIENT_ATTENTION,
                "math": SDPBackend.MATH, "cudnn": SDPBackend.CUDNN_ATTENTION}
    context = nullcontext() if args.sdpa_backend == "auto" else sdpa_kernel(backends[args.sdpa_backend])
    functional.scaled_dot_product_attention = traced
    original_argv = sys.argv
    try:
        sys.argv = [sys.argv[0], *remaining]
        with context:
            benchmark()
    finally:
        sys.argv = original_argv
        functional.scaled_dot_product_attention = original


if __name__ == "__main__":
    main()
