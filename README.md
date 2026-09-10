# Ref2VA Consumer GPU Deployment

Deployment notes and benchmark protocol for running a Ref2VA (Reference-to-Video/Audio)
pipeline with **MiniMax-H3** on consumer-class GPUs.

This repository contains **deployment material only**: hardware requirements, worker
layout, environment setup, and the benchmark methodology behind the numbers below.
It does **not** contain any product, content, or business logic.

## The headline

> Three RTX 5090-class GPUs. 28.25 seconds of MiniMax-H3 video. 20.70 seconds wall clock.
>
> That's RTF 0.733 — the pipeline produced native video faster than a player would consume it.
>
> Not a datacenter flex. Just three consumer-class GPUs running Ref2VA workers in parallel.

**Output spec:** 608×352 · 226 frames · 24 FPS · 4 steps · native stereo audio.

**Measurement:** three successful batches after warmup — 20.703s / 20.821s / 20.575s.
Measured from submission to terminal ComfyUI receipt; model loading and download excluded.

## What's in this repo

| Path | Content |
|---|---|
| `docs/hardware.md` | GPU / host requirements and how to size the fleet |
| `docs/architecture.md` | Worker layout, queue model, and failure semantics |
| `docs/benchmark.md` | Exact benchmark protocol so the numbers are reproducible |
| `docs/faq.md` | Common questions (precision, scaling, single-GPU fallback) |
| `deploy/` | Generic install scripts and environment templates |
| `config/` | Worker configuration templates |

## Design principles

1. **One GPU, one worker.** No model sharing across processes; each ComfyUI worker
   owns a full GPU. Parallelism comes from the queue, not from tensor splitting.
2. **Everything addressable is an IP:port.** Workers register by URL; nothing in the
   config depends on where a machine physically lives.
3. **Warm models stay warm.** Model load time is excluded from the benchmark and from
   steady-state throughput planning. Workers are long-lived processes.
4. **The receipt is the contract.** A job is done when the orchestrator receives the
   terminal receipt from ComfyUI — not when the last frame is rendered.

## Quick start

See `deploy/README.md` for the full walkthrough. In short:

```bash
# on each GPU host
./deploy/setup_worker.sh            # installs deps, downloads MiniMax-H3 weights
./deploy/run_worker.sh --gpu 0      # one worker per GPU

# on the orchestrator host
cp config/orchestrator.env.example config/orchestrator.env
# edit: list worker URLs, one per GPU
./deploy/run_orchestrator.sh
```

Then benchmark with the protocol in `docs/benchmark.md`.
