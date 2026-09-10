# Hardware

## Reference configuration

The headline numbers (RTF 0.733 for a 28.25s clip) were measured on:

| Component | Spec |
|---|---|
| GPUs | 3 × RTX 5090-class (32 GB VRAM each) |
| Host RAM | ≥ 96 GB total (weights staging + audio pipeline) |
| Storage | ≥ 150 GB free, NVMe recommended (model weights ~90 GB) |
| Network | Any LAN; workers are reached by plain HTTP |

The GPUs may live in one chassis or be spread across multiple machines — the
pipeline does not care. Workers register by URL, so a single 3-GPU box and three
1-GPU boxes are operationally identical.

## Sizing rules

- **VRAM:** MiniMax-H3 at 608×352 / 226 frames / 4 steps fits in 32 GB with room
  for the audio stack. 24 GB cards are not supported for this profile.
- **One worker per GPU.** Do not colocate two workers on one GPU; VRAM contention
  turns throughput into a lottery.
- **CPU:** unremarkable. Orchestration and audio muxing are not CPU-bound; any
  modern 8-core CPU keeps up with three workers.
- **Bandwidth between workers:** none required. Workers never talk to each other;
  all coordination goes through the orchestrator's queue.

## Scaling

Throughput scales ~linearly with worker count until the orchestrator's submission
path saturates (not observed below 8 workers).

| GPUs | Expected throughput (this workload) |
|---|---|
| 1 | ~1.5 min per 28.25s clip (single-worker, sequential batches) |
| 3 | RTF 0.733 (reference measurement) |
| N | Clip sharding keeps wall clock roughly constant; queue depth grows |

## Single-GPU fallback

The pipeline works on one GPU — the orchestrator simply serializes batch shards.
Expect wall clock to scale with shard count. Everything else (workflow JSON,
receipt contract, benchmark protocol) is unchanged.
