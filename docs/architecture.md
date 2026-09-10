# Architecture

```
            ┌────────────────────┐
            │    Orchestrator    │
            │  (queue + submit)  │
            └─────────┬──────────┘
              HTTP    │    HTTP (receipt)
      ┌───────────────┼───────────────┐
      ▼               ▼               ▼
┌───────────┐   ┌───────────┐   ┌───────────┐
│ Worker 0  │   │ Worker 1  │   │ Worker 2  │
│ ComfyUI   │   │ ComfyUI   │   │ ComfyUI   │
│ GPU 0     │   │ GPU 1     │   │ GPU 2     │
└───────────┘   └───────────┘   └───────────┘
```

A queue in front of N independent ComfyUI instances. No shared filesystem, no
worker-to-worker traffic, no service discovery — workers are a static list of
URLs.

## Orchestrator

- Owns the job and the worker registry (`config/orchestrator.json`).
- Shards a batch across idle workers, submits each clip via `POST /prompt`,
  and polls `/history/<prompt_id>` until terminal.
- Downloads the MP4, probes the envelope (frame count, fps, codec), transcodes
  to the delivery format, and writes a receipt.

## Worker

- Stock ComfyUI pinned to one GPU, weights resident.
- Exposes only the standard ComfyUI API plus the MiniMax-H3 node pack.
- Knows nothing about the other workers.

## Concurrency and deadlock avoidance

A lane waits on its clip's **Future with the remaining deadline**, never on a
bare `Event` for the clip to report "submitted". If a clip thread raises, the
exception propagates to the batch immediately; the batch fails or retries
instead of a lane blocking until the deadline while its clip thread is already
gone. This is the failure mode the orchestrator is designed to avoid: a crashed
clip must never look like a slow clip.

## Job lifecycle

1. **Wait idle** — all workers report empty run/pending queues.
2. **Upload** — reference images/audio/first/last frames, cached per worker.
3. **Dispatch** — one workflow per clip, `t_submit` recorded.
4. **Poll** — `/history` until terminal success/error per clip.
5. **Download + validate** — MP4 fetched, envelope probed, retried up to 3×.
6. **Transcode** — to delivery H.264/AAC at the delivery fps.
7. **Receipt** — wall clock, per-clip execution seconds, RTF.

## Failure semantics

- Clip raises → batch fails fast with the error; the lane does not hang.
- Download/validation fails → retried up to 3 times, then raised.
- Deadline exceeded anywhere → `TimeoutError`, batch fails.
