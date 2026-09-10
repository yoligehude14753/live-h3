# Deploy

Generic deployment scripts for the Ref2VA + MiniMax-H3 worker fleet.

Everything here is machine-agnostic: workers are configured by GPU index and
port, the orchestrator by a list of worker URLs. No hostnames, no hardcoded
addresses anywhere — all addressing comes from `config/orchestrator.env`.

## Layout

| Script | Runs on | Purpose |
|---|---|---|
| `setup_worker.sh` | each GPU host | install deps, fetch MiniMax-H3 weights |
| `run_worker.sh` | each GPU host | start one ComfyUI worker pinned to one GPU |
| `run_orchestrator.sh` | orchestrator host | start queue + dispatcher |
| `benchmark.sh` | orchestrator host | run the protocol from `docs/benchmark.md` |

## Walkthrough

### 1. Set up each GPU host

```bash
./setup_worker.sh
```

Creates a Python venv in `./.venv`, installs ComfyUI plus the MiniMax-H3
custom nodes, and downloads the weights into `./models/` (~90 GB).

### 2. Start one worker per GPU

```bash
./run_worker.sh --gpu 0 --port 8188
./run_worker.sh --gpu 1 --port 8189   # same box, second GPU
# or on another machine:
./run_worker.sh --gpu 0 --port 8188
```

`run_worker.sh` sets `CUDA_VISIBLE_DEVICES` and refuses to start if the
port is already taken — two workers on one GPU is a configuration error,
not a throughput strategy.

### 3. Configure the orchestrator

```bash
cp ../config/orchestrator.env.example ../config/orchestrator.env
```

Edit the worker list — one URL per GPU, for example:

```
WORKER_URLS=http://192.0.2.10:8188,http://192.0.2.10:8189,http://192.0.2.11:8188
```

(Use your own hosts' addresses. These are example IPs only.)

### 4. Warm up, then benchmark

```bash
./run_orchestrator.sh        # leave running
./benchmark.sh --runs 1      # warmup (not timed)
./benchmark.sh --runs 3      # timed runs, prints RTF
```

## Requirements

- Linux, NVIDIA driver ≥ 560, CUDA ≥ 12.4
- Python ≥ 3.10
- ~150 GB free disk per worker host for weights + outputs
