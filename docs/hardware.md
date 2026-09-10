# Hardware

## Reference configuration

The headline numbers were measured on three RTX 5090-class GPUs (32 GB VRAM
each), one ComfyUI worker per GPU.

| Component | Requirement |
|---|---|
| GPU VRAM | ≥ 32 GB per worker for the reference profile |
| Host RAM | ≥ 96 GB total (weight staging + audio pipeline) |
| Disk | ≥ 150 GB free, NVMe recommended (weights ≈ 90 GB) |
| Software | Linux, NVIDIA driver ≥ 560, CUDA ≥ 12.4, Python ≥ 3.10, ffmpeg + ffprobe |
| Network | plain LAN; workers reached by HTTP only |

GPUs may share a chassis or be spread across machines — a worker is just a URL,
the orchestrator does not care about physical topology.

## Required weights

Place these under the worker's models directory (names must match the profile):

| Profile key | File |
|---|---|
| `unet` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| `lora` | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` |
| `text_encoder` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| `video_vae` | `minimax_h3_video_vae_fp16.safetensors` |
| `audio_vae` | `minimax_h3_audio_vae_fp32.safetensors` |

Check the upstream MiniMax-H3 license before redistributing or deploying weights.

## Required custom nodes

The workflow uses these ComfyUI class types, provided by the MiniMax-H3 node pack:
`MiniMaxH3ReferenceToVideo`, `MiniMaxH3ImageToVideo`, `MiniMaxH3SigmaShift`,
`MiniMaxH3AddGuide`, `SaveVideo`, `CreateVideo`, `VAEDecodeAudio`, `AudioAdjustVolume`.

## Sizing rules

- **One worker per GPU.** Two workers sharing a GPU contend on VRAM and turn
  throughput into a lottery. `run_worker.sh` refuses to double-book a port.
- **Warm models stay warm.** Model load is excluded from steady-state numbers;
  workers are long-lived.
- **CPU is unremarkable.** Orchestration, download, and transcode are not
  CPU-bound; any modern 8-core keeps up with three workers.
- **No worker-to-worker traffic.** All coordination goes through the orchestrator.

## Scaling

Throughput scales ~linearly with worker count for batch sharding. A single GPU
works — the orchestrator serializes shards and wall clock scales with shard count.
