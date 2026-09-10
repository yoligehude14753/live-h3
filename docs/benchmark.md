# Benchmark protocol

The numbers in the README are only meaningful under this protocol.
If you report numbers from your own deployment, follow the same rules
so results are comparable.

## Workload

| Parameter | Value |
|---|---|
| Model | MiniMax-H3 |
| Resolution | 608×352 |
| Frames | 226 |
| Frame rate | 24 FPS (clip duration 28.25s with audio tail) |
| Sampling steps | 4 |
| Audio | native stereo |
| Reference input | fixed across runs |

## Timing rules

- **Start:** orchestrator dispatches the first shard (`t_submit`).
- **End:** orchestrator holds terminal ComfyUI receipts for all shards
  (`max(t_receipt)`).
- **Excluded:** model loading, weight download, environment setup.
  Workers are warmed up before timing starts.
- **Warmup:** at least one full job must complete before any timed run.
- **Validity:** a timed run counts only if the job completes successfully —
  all shards rendered, audio present, output playable.

## Reference measurement

Three successful batches after warmup:

| Run | Wall clock |
|---|---|
| 1 | 20.703 s |
| 2 | 20.821 s |
| 3 | 20.575 s |

Median: **20.70 s** for 28.25 s of output → **RTF 0.733**
(RTF = wall clock / output duration; < 1.0 means faster than real-time playback).

## Reporting template

When publishing your own numbers, include:

1. GPU model and count.
2. Full workload table (resolution / frames / steps / audio).
3. Warmup statement ("N jobs completed before timing").
4. All individual run times, not just the best.
5. The exact timing contract (submission → terminal receipt; loading excluded).

Numbers without these five items are marketing, not benchmarks.

## Reproducing

```bash
# workers running and warmed (see deploy/README.md)
./deploy/benchmark.sh --runs 3 --config config/orchestrator.env
```

The script prints per-run wall clock, per-shard receipt times, and the
resulting RTF, plus a machine-readable `benchmark_result.json`.
