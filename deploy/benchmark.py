#!/usr/bin/env python3
"""Run the benchmark protocol: N timed batches, submission -> terminal receipt.

Model loading and weight download are excluded; run one warmup batch first.
Prints per-run wall clock and RTF plus a machine-readable benchmark_result.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ref2va_deploy import ThreeLaneOrchestrator  # noqa: E402


def load_job(path: str | None, profile: dict) -> dict:
    if path:
        return json.loads(Path(path).read_text())
    # Minimal smoke job: no references, text prompt only. Requires weights to
    # accept zero reference images; supply --job for a real measurement.
    return {"name": "smoke", "prompt": "a still room, no people, ambient sound",
            "image_references": [], "audio_references": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--job", default=None, help="job JSON; defaults to a text-only smoke job")
    ap.add_argument("--out", default="benchmark_result.json")
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text())
    orch = ThreeLaneOrchestrator(config, Path(config.get("runtime_root", "./runtime")))
    duration = float(config["profile"]["duration_seconds"])
    deadline_seconds = float(config.get("deadline_seconds", 600))

    job = load_job(args.job, config["profile"])
    jobs = [dict(job, name=f"{job.get('name', 'clip')}-{i}") for i in range(len(config["workers"]))]

    print("[benchmark] warmup run (not timed)")
    orch.render_batch(jobs, time.time() + deadline_seconds)

    runs = []
    for i in range(args.runs):
        deadline = time.time() + deadline_seconds
        receipt = orch.render_batch(jobs, deadline)
        wall = receipt["wall_seconds"]
        runs.append({"run": i + 1, "wall_seconds": wall, "rtf": round(wall / duration, 4)})
        print(f"[benchmark] run {i + 1}: wall={wall:.3f}s rtf={wall / duration:.3f}")

    result = {"duration_seconds": duration, "runs": runs,
              "median_wall_seconds": sorted(r["wall_seconds"] for r in runs)[len(runs) // 2]}
    result["median_rtf"] = round(result["median_wall_seconds"] / duration, 4)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(f"[benchmark] median wall={result['median_wall_seconds']:.3f}s "
          f"RTF={result['median_rtf']:.3f} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
