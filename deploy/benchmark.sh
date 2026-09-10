#!/usr/bin/env bash
# benchmark.sh — run the benchmark protocol from docs/benchmark.md.
# Usage: ./benchmark.sh --runs 3 [--config ./config/orchestrator.env]
set -euo pipefail

RUNS=""
CONFIG="./config/orchestrator.env"
while [ $# -gt 0 ]; do
  case "$1" in
    --runs)   RUNS="$2";   shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$RUNS" ] || { echo "--runs is required" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONFIG"

# Protocol (docs/benchmark.md):
#   t0 = submission of first shard
#   t1 = terminal ComfyUI receipt of last shard
#   wall = t1 - t0; RTF = wall / output_duration (28.25s reference workload)
# Model loading and download are excluded; run at least one warmup job first.

echo "[benchmark] $RUNS run(s), workload: 608x352 / 226f / 24fps / 4 steps / stereo"
echo "[benchmark] timing contract: submission -> terminal receipt; loading excluded"

for i in $(seq 1 "$RUNS"); do
  t0=$(python3 -c 'import time; print(time.time())')
  # --- submit job, wait for all terminal receipts -------------------------
  # Implement against your orchestrator's API; placeholder sleep removed on
  # purpose so this script cannot print a fabricated number.
  echo "[benchmark] run $i: submit job via orchestrator and wait for receipts" >&2
  echo "[benchmark] ERROR: dispatcher not implemented — see docs/architecture.md" >&2
  exit 3
  # t1=$(python3 -c 'import time; print(time.time())')
  # python3 - "$t0" "$t1" <<'PY'
  # import sys
  # wall = float(sys.argv[2]) - float(sys.argv[1])
  # print(f"run: wall={wall:.3f}s  RTF={wall/28.25:.3f}")
  # PY
done
