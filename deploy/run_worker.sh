#!/usr/bin/env bash
# Start one ComfyUI worker pinned to exactly one GPU.
# Usage: ./run_worker.sh --gpu 0 --port 8188
set -euo pipefail

GPU=""; PORT="8188"
COMFYUI_DIR="${COMFYUI_DIR:-./ComfyUI}"
VENV_DIR="${VENV_DIR:-./.venv}"

while [ $# -gt 0 ]; do
  case "$1" in
    --gpu)  GPU="$2";  shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$GPU" ] || { echo "--gpu is required" >&2; exit 2; }

if command -v lsof >/dev/null && lsof -nP -iTCP:"$PORT" >/dev/null 2>&1; then
  echo "port $PORT already in use; refusing to start a second worker on it" >&2
  exit 1
fi

# shellcheck disable=SC1091
[ -f "$VENV_DIR/bin/activate" ] && source "$VENV_DIR/bin/activate"
echo "[run_worker] GPU=$GPU PORT=$PORT"
CUDA_VISIBLE_DEVICES="$GPU" exec python "$COMFYUI_DIR/main.py" --listen 0.0.0.0 --port "$PORT"
