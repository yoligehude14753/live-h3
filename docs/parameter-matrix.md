# Parameter matrix

How the video parameters map to quality, speed, and hardware needs. The
reference profile is the validated configuration; the other rows are supported
levers and their expected effect. Treat non-reference rows as starting points —
re-benchmark on your own hardware before quoting numbers.

## The levers

| Parameter | Profile key | Drives |
|---|---|---|
| Resolution | `source_width` / `source_height` | VRAM, per-frame cost, detail |
| Frame count | `num_frames` | clip duration, VRAM (temporal), wall clock |
| Frame rate | `native_fps` (gen) / `fps` (delivery) | duration, motion smoothness |
| Sampling steps | `num_inference_steps` | quality vs speed (near-linear) |
| Sampler / scheduler | `sampler` / `scheduler` | convergence behavior |
| Shift | `shift_video` / `shift_audio` | temporal vs detail emphasis |
| References | image / audio / first / last frame | identity & continuity vs prompt adherence |

## Configurations

### Reference (validated) — 360p, 4-step turbo

| Field | Value |
|---|---|
| Resolution | 608×352 → 640×360 |
| Frames / native fps | 226 / 24 |
| Steps | 4 |
| LoRA | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16` |
| UNet | `minimax_h3_ref2va_pruned_int8_convrot` |
| shift_video / shift_audio | 12.0 / 3.0 |
| VRAM | fits 32 GB |
| Measured | RTF 0.733 (3-lane block, 28.25s out); best block RTF 0.231 |

This is the only configuration with published measurements. The 4-step turbo
LoRA is what makes RTF < 1 possible; the pruned int8 UNet is what makes it fit
on a consumer card.

### Higher quality — 8–12 steps

| Change | Effect |
|---|---|
| `num_inference_steps: 8–12` | finer detail, fewer artifacts at motion boundaries |
| wall clock | scales ~linearly with steps (8 steps ≈ 2× the 4-step time) |
| VRAM | unchanged |
| turbo LoRA | keep it; it is a distillation LoRA, still helps at higher steps |

Expect RTF to rise above 1.0 on the same hardware. Use when output quality
matters more than faster-than-realtime generation.

### Higher resolution — 480p class

| Change | Effect |
|---|---|
| `source_width/height: ~768×448` | noticeably sharper output |
| VRAM | rises sharply; 32 GB is tight, may require a lower frame count |
| wall clock | per-frame cost up; RTF rises |
| `ref_image_size: "match"` | keep references matched to the source resolution |

### Longer clip — more frames

| Change | Effect |
|---|---|
| `num_frames: 226 → 300+` | longer single clip |
| VRAM | temporal dimension grows; the main VRAM pressure after resolution |
| wall clock | roughly linear in frames at fixed steps |
| duration | recompute `duration_seconds = num_frames / native_fps` |

On 32 GB, long clips at high resolution will not both fit; trade one against the
other.

### Single GPU fallback

| Change | Effect |
|---|---|
| 1 worker instead of 3 | same workflow, same receipt contract |
| wall clock | a 3-clip batch serializes; wall ≈ 3× single-clip time |
| throughput | ~1/3 of the three-lane fleet |

## What actually moves the needle

1. **Steps** is the dominant wall-clock lever at fixed resolution — near-linear.
2. **Resolution** is the dominant VRAM lever, then **frame count**.
3. **The turbo LoRA + pruned int8 UNet** are the difference between datacenter
   and consumer-class feasibility. Without them this profile does not hit RTF < 1.
4. **References** (identity / environment / voice / first / last frame) cost a
   small upload and conditioning overhead but do not change sampling cost; use
   them freely for continuity.

## Production telemetry reference

Same reference profile, 491 production blocks (3 parallel clips, 28.25s out):

| Metric | generation_seconds | block RTF |
|---|---|---|
| min | 10.63 | 0.231 |
| p50 | 32.62 | 0.923 |
| p95 | 64.56 | 1.722 |

The gap between the p50 (~0.92) and the controlled benchmark (0.733) is
operational: worker stalls, cold lanes, and upload retries. Steady-state
hardware capability is the benchmark number; production adds the tail.
