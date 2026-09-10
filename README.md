# Ref2VA Consumer GPU Deployment

Deployment and benchmark tooling for running **MiniMax-H3 Ref2VA**
(reference-to-video/audio) on consumer-class GPUs. One ComfyUI worker per GPU,
a queue in front, and a benchmark protocol that times *submission → terminal
receipt* with model loading excluded.

This repo is **deployment-only**: no story, voting, or scheduling logic — just
workers, an orchestrator, and a reproducible benchmark.

> Three RTX 5090-class GPUs. 28.25 seconds of MiniMax-H3 video. 20.70 seconds wall clock.
>
> That's RTF 0.733 — the pipeline produced native video faster than a player would consume it.
>
> Not a datacenter flex. Just three consumer-class GPUs running Ref2VA workers in parallel.

**Workload:** 608×352 · 226 frames · 24 FPS · 4 steps · native stereo audio.
**Measurement:** three successful batches after warmup — 20.703s / 20.821s / 20.575s,
submission → terminal ComfyUI receipt; model loading and download excluded.

## Layout

| Path | Content |
|---|---|
| `src/ref2va_deploy/worker_client.py` | ComfyUI HTTP/WS client: submit, poll, upload, result parse |
| `src/ref2va_deploy/orchestrator.py` | Three-lane orchestrator + Ref2VA workflow builder |
| `deploy/setup_worker.sh` | Install ComfyUI + deps on a GPU host |
| `deploy/run_worker.sh` | Start one worker pinned to one GPU |
| `deploy/benchmark.py` | The benchmark protocol (warmup + N timed runs → RTF) |
| `config/orchestrator.example.json` | Full media profile + worker list |
| `docs/hardware.md` | GPU/host sizing |
| `docs/benchmark.md` | Exact timing contract |
| `docs/parameter-matrix.md` | Video-parameter configurations and their effects |
| `docs/reproduction.md` | Step-by-step third-party reproduction |

## Quick start

```bash
# each GPU host
./deploy/setup_worker.sh
./deploy/run_worker.sh --gpu 0 --port 8188

# orchestrator host
cp config/orchestrator.example.json config/orchestrator.json   # edit worker URLs
python3 deploy/benchmark.py --config config/orchestrator.json --runs 3
```

See `docs/reproduction.md` for the full walkthrough.

## Timing contract

Wall clock = submission of the batch → terminal receipt of the last clip.
RTF = wall / output duration. A run counts only if every clip completes with a
valid H.264/AAC delivery envelope. Full rules in `docs/benchmark.md`.

## Production telemetry

Beyond the headline benchmark, the same profile has run continuously in
production. Across **491 blocks** (3 parallel clips each, 28.25s output):

| Metric | generation_seconds | block RTF |
|---|---|---|
| min | 10.63 | 0.231 |
| p50 | 32.62 | 0.923 |
| p95 | 64.56 | 1.722 |

Best-observed single-block wall clock is 10.63s for 28.25s of output (RTF 0.231).
The p50 sits just under real-time; the tail reflects worker stalls and cold
lanes, not steady-state throughput. See `docs/parameter-matrix.md`.
