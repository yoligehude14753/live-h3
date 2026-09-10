# Architecture

## Overview

```
            ┌────────────────────┐
            │    Orchestrator    │
            │  (queue + submit)  │
            └─────────┬──────────┘
              HTTP    │    HTTP (receipt webhook)
      ┌───────────────┼───────────────┐
      ▼               ▼               ▼
┌───────────┐   ┌───────────┐   ┌───────────┐
│ Worker A  │   │ Worker B  │   │ Worker C  │
│ ComfyUI   │   │ ComfyUI   │   │ ComfyUI   │
│ GPU 0     │   │ GPU 1     │   │ GPU 2     │
└───────────┘   └───────────┘   └───────────┘
```

Deliberately boring: a queue in front of N independent ComfyUI instances.
No shared filesystem requirement, no worker-to-worker traffic, no service
discovery — workers are configured as a static list of URLs.

## Components

### Orchestrator

- Owns the job queue and the worker registry (`config/orchestrator.env`).
- Splits a job into per-worker batch shards and submits via the ComfyUI
  HTTP API (`POST /prompt`).
- Collects terminal receipts (websocket or polling on `/history`) and
  declares the job complete when all shards have terminal receipts.
- Stateless apart from the in-flight queue; safe to restart mid-job
  (in-flight shards are re-queued).

### Worker

- A stock ComfyUI instance pinned to one GPU (`CUDA_VISIBLE_DEVICES`).
- Loads MiniMax-H3 weights once at startup and keeps them resident.
- Exposes only the standard ComfyUI API. No custom plugins are required
  beyond the model's custom nodes.
- Knows nothing about the other workers.

## Job lifecycle

1. **Submit** — orchestrator accepts a job (reference input + params).
2. **Shard** — the frame range is split into contiguous shards, one per idle worker.
3. **Dispatch** — each shard becomes one ComfyUI prompt; `t_submit` is recorded.
4. **Execute** — workers render independently.
5. **Receipt** — orchestrator receives the terminal receipt per shard;
   `t_receipt` is recorded per shard.
6. **Assemble** — shard outputs are concatenated in frame order; audio is
   muxed from the native stereo track.
7. **Done** — wall clock for the benchmark is `max(t_receipt) - min(t_submit)`.

## Failure semantics

- **Worker dies mid-shard:** the shard times out, is re-queued to a healthy
  worker. The job slows down; it does not fail.
- **Orchestrator dies:** workers finish their shards into the void; on restart
  the orchestrator re-queues everything that lacked a terminal receipt.
  Duplicate receipts are deduplicated by prompt ID.
- **Bad output (OOM, NaN frames):** the shard is marked failed, not retried
  blindly — three failures of the same shard fails the job.

## What this design explicitly avoids

- Tensor parallelism / model sharding across GPUs (latency win is real but
  the ops cost is not worth it at this scale).
- A shared model server. Each worker owns its weights; there is nothing to
  coordinate.
- Any dependence on machine identity. A worker is a URL.
