# Benchmark protocol

These rules make the headline numbers comparable across machines. If you report
numbers from your own deployment, follow them and publish the same fields.

## Workload

| Parameter | Value |
|---|---|
| Model | MiniMax-H3 Ref2VA |
| Resolution | 608×352 (source) → 640×360 (delivery) |
| Frames | 226 |
| Native frame rate | 24 FPS |
| Sampling steps | 4 (euler / simple) |
| Audio | native stereo |
| Batch | 3 clips in parallel, one per lane |

**Output-duration convention.** A block of 3 parallel clips is reported as
28.25s of output (`block_duration_seconds`). A single 226-frame clip at native
24 FPS is 9.417s. The headline 20.70s / RTF 0.733 uses the 28.25s block
convention (3 lanes producing in parallel). Single-clip RTF divides wall clock
by 9.417s instead. Pick one convention and state it.

## Timing rules

- **Start:** orchestrator dispatches the batch (`t_submit`).
- **End:** orchestrator holds terminal receipts for all clips (`max(t_receipt)`).
- **Excluded:** model loading, weight download, environment setup — workers are
  warmed before timing.
- **Warmup:** at least one full batch must complete before any timed run.
- **Validity:** a run counts only if every clip completes and passes the
  delivery-envelope probe (H.264 video, AAC audio, exact frame count and fps).

## Reference measurement

Three successful batches after warmup: 20.703s / 20.821s / 20.575s.
Median 20.70s for 28.25s of output → **RTF 0.733**.

## Reporting template

1. GPU model and count.
2. Full workload table (resolution / frames / fps / steps / audio).
3. The duration convention (single-clip vs parallel-block).
4. Warmup statement.
5. All individual run times, not just the best.
6. The timing contract (submission → terminal receipt; loading excluded).

Numbers without these six items are marketing, not benchmarks.

## Reproducing

```bash
python3 deploy/benchmark.py --config config/orchestrator.json --runs 3
```

Prints per-run wall clock and RTF, plus `benchmark_result.json` with the median.
