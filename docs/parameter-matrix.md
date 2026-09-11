# Parameter matrix

How the video parameters map to quality, speed, and hardware needs. The
reference profile is the validated configuration. Measured rows are labeled
with their data provenance; rows without a measured value are levers and their
expected effect, not measurements.

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
| Input mode | text-to-video / image-to-video / reference | conditioning path |

## Measured configuration tiers

All rows below are real measurements from the deployment fleet, with their
provenance. Where a tier was never measured, that is stated — no number is
extrapolated or invented.

### Resolution / duration tiers (single GPU unless noted)

| Tier | Resolution | Frames / fps | Steps | Precision | Duration | Time | Provenance |
|---|---|---|---|---|---|---|---|
| 360p turbo | 608×352 | 124 / 24 | 4 | int8 + turbo LoRA | 5.167 s | exec 9.31–9.46 s, submit→receipt 10.16–10.31 s | sample-run receipts |
| 768p short-drama | 768×1344 | 360 / 24 | 30 | fl2va | 15.0 s | submit→complete 1614–1956 s (median 1945 s) | production queue ledger, 13 shots |
| 768p full | 1344×768 | 120 / 24 | 50 | bf16 (unoptimized) | 5.0 s | denoise 461.9 s (49 steps) | early validation record |
| 1080p | — | — | — | — | — | **never measured** | — |

Reading the tiers:

- **360p turbo** is the only tier that runs faster than real-time. 5.167s of
  output in ~9.3s of execution (~10.2s submit→receipt) on one card — already
  near real-time on a single GPU, which is why three lanes in parallel break
  RTF 1.0 (see the headline benchmark).
- **768p short-drama** is the high-quality production tier: 30 steps, 15s
  vertical clips, ~27–33 minutes per shot on a single card (RTF ≈ 130). This is
  offline/batch work, not real-time — quality over speed.
- **768p full bf16 at 50 steps** is the unoptimized baseline from early
  validation (~462s denoise for 5s), shown for contrast against what the
  turbo LoRA + int8 path achieves at 360p.
- **1080p was never run.** Do not quote a number for it.

The 360p→768p gap illustrates the super-linear resolution cost: 768×1344 has
~4.8× the pixels of 608×352, and at higher steps the per-shot time goes from
~10s to ~1900s — resolution and steps compound, they do not add.

### Input mode at 360p (text vs image vs reference)

At the reference 360p profile the conditioning path (text-to-video,
image-to-video, or one reference image) does not measurably change sampling
time — the reference/sample runs all land in the same ~9.3–9.5s execution band
for 5.167s of output. Conditioning overhead is negligible next to sampling, so
references are used freely for continuity. Resolution and steps, not input
mode, are what move the clock.

### Reference-input dimension (360p, 4-step turbo, single GPU)

How the number and kind of reference inputs affect execution time. All rows are
measured runs with receipts. "Guide" = a first/last-frame image injected via the
frame-guide node; "chained" = each clip's first frame is the previous clip's
last frame.

| References | Audio ref | Guide | Frames | Exec time | Provenance |
|---|---|---|---|---|---|
| 1 image | 0 | none | 124 | 9.31 s | sample-run workflow + receipt |
| 1 image | 0 | first-frame (chained) | 124 | 9.35 / 9.46 s | sample-run workflow + receipt |
| 1 image (character) | 0 | first-frame (chained) | 226 | 17.78–20.01 s (18 runs) | daily continuity runs, mode "sequential first-frame chained Ref2VA" |
| (refs not archived) | — | none | 226 | 16.87–19.16 s (21 runs) | run-01..04 speed/visual batches |
| (frame-grid prompt) | — | none | 209 | 16.31 / 15.41 s | frame-grid sweep |
| 2 images | 1 | none | 209 | 30.13 s (submit→complete 32.13 s) | ref2va multi-ref canary |

Reading the dimension:

- **First/last-frame guides are essentially free.** Guided clips land in the
  same execution band as unguided clips at the same frame count — 9.35–9.46s vs
  9.31s at 124 frames, and at 226 frames the chained Ref2VA runs with a
  first-frame guide (17.78–20.01s) overlap the unguided speed/visual batches
  (16.87–19.16s). Use frame guides freely for temporal continuity; they cost
  nothing measurable.
- **A second reference image roughly doubles the cost.** At 209 frames, the
  two-reference-image + one-audio-reference canary runs at ~30s execution versus
  ~16s for the frame-grid prompt at the same frame count. Each extra reference
  image is encoded and cross-attended, and unlike the frame guide it is not
  free. (The frame-grid tier's exact reference composition is not archived, so
  this comparison is indicative, not a controlled A/B.)

### Frame-count sweep (608×352, 24fps, 4-step turbo, single GPU)

Two runs per tier; block RTF is the two-worker worst case. Source: production
experiment ledger.

| Frames | Clip length | Run 1 | Run 2 | Block RTF |
|---|---|---|---|---|
| 124 | 5.167 s | 8.898 s | 8.039 s | 0.861 |
| 141 | 5.875 s | 10.259 s | 9.383 s | 0.873 |
| 158 | 6.583 s | 11.668 s | 10.827 s | 0.886 |
| 175 | 7.292 s | 13.210 s | 12.318 s | 0.906 |
| 192 | 8.000 s | 14.670 s | 13.684 s | 0.917 |
| 209 | 8.708 s | 16.311 s | 15.413 s | 0.936 |
| 243 | 10.125 s | 19.700 s | 18.774 s | 0.973 / 0.927 |

Execution grows ~linearly with frames (~0.075 s/frame at this profile); RTF
degrades slowly since output duration grows in step. 243 frames passes RTF < 1
with under 3% margin — not chosen for production. 226 frames / 9.417s is the
selected operating point.

## Reference profile (validated) — 360p, 4-step turbo

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

This is the only configuration with a controlled multi-run benchmark. The 4-step
turbo LoRA makes RTF < 1 possible; the pruned int8 UNet makes it fit on a
consumer card.

## What actually moves the needle

1. **Resolution** is the dominant wall-clock *and* VRAM lever — super-linear
   (see the 360p→768p tier gap). This is the single biggest cost knob.
2. **Steps** scales wall clock near-linearly at fixed resolution.
3. **Frame count** scales execution near-linearly; RTF degrades only mildly since
   output duration grows too.
4. **Input mode** (text / image / reference) is negligible at a given resolution —
   use references freely for continuity; they do not change sampling cost.
5. **The turbo LoRA + pruned int8 UNet** are the difference between datacenter
   and consumer-class feasibility. Without them this profile does not hit RTF < 1.

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

## Single GPU fallback

| Change | Effect |
|---|---|
| 1 worker instead of 3 | same workflow, same receipt contract |
| wall clock | a 3-clip batch serializes; wall ≈ 3× single-clip time |
| throughput | ~1/3 of the three-lane fleet |
