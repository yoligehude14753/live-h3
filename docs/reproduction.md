# Third-party reproduction

Follow this to reproduce the benchmark on your own hardware.

## 1. Prepare each GPU host

```bash
./deploy/setup_worker.sh
```

Installs ComfyUI, PyTorch (cu124), and the Python deps. Then:

- Install the MiniMax-H3 custom-node pack into `ComfyUI/custom_nodes/` (the
  class types listed in `docs/hardware.md` must be importable).
- Download the five weight files into the worker's models directory, names
  exactly as in the profile.

## 2. Start one worker per GPU

```bash
./deploy/run_worker.sh --gpu 0 --port 8188
```

Repeat per GPU (same host or different hosts). Each worker binds one GPU via
`CUDA_VISIBLE_DEVICES` and refuses to start on an occupied port.

Verify each worker:

```bash
curl -s http://<host>:8188/system_stats
```

## 3. Configure the orchestrator

```bash
cp config/orchestrator.example.json config/orchestrator.json
```

Set `workers` to your URLs (one per GPU) and `runtime_root` to a writable path.
Leave the `profile` block at the reference values to reproduce the headline
numbers.

## 4. Warm up, then measure

```bash
python3 deploy/benchmark.py --config config/orchestrator.json --runs 3
```

The script runs one warmup batch (untimed), then `--runs` timed batches, and
writes `benchmark_result.json`. Supply a real job for a faithful measurement:

```bash
python3 deploy/benchmark.py --config config/orchestrator.json --runs 3 --job my_job.json
```

A job is JSON:

```json
{
  "name": "scene-01",
  "prompt": "<Subject 1> is the person in <Picture 1>. ...",
  "image_references": ["/abs/path/ref.png"],
  "audio_references": ["/abs/path/voice.wav"],
  "first_frame": "/abs/path/first.png",
  "last_frame": "/abs/path/last.png"
}
```

Reference files are uploaded to the worker once and cached in
`runtime/reference_uploads.json`.

## 5. Report

Publish the six fields from `docs/benchmark.md` (GPU, workload table, duration
convention, warmup statement, all run times, timing contract) so your numbers
are comparable to the reference measurement.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `media envelope mismatch` | worker dropped frames; check VRAM headroom / OOM |
| `completed without an MP4` | `SaveVideo` node missing or output type mismatch |
| `reference cache miss` | upload disabled and file not pre-staged on worker |
| deadline exceeded on one lane | that worker stalled; check its `/queue` and GPU |
