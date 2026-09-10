#!/usr/bin/env bash
# setup_worker.sh — install a Ref2VA/MiniMax-H3 ComfyUI worker.
# Idempotent: safe to re-run. Machine-agnostic; no hostnames or addresses.
set -euo pipefail

VENV_DIR="${VENV_DIR:-./.venv}"
MODELS_DIR="${MODELS_DIR:-./models}"
COMFYUI_DIR="${COMFYUI_DIR:-./ComfyUI}"

log() { printf '[setup_worker] %s\n' "$*"; }

command -v python3 >/dev/null || { log "python3 required (>=3.10)"; exit 1; }
command -v git >/dev/null || { log "git required"; exit 1; }
command -v nvidia-smi >/dev/null || { log "NVIDIA driver not found"; exit 1; }

log "GPUs visible on this host:"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader

# --- ComfyUI -------------------------------------------------------------
if [ ! -d "$COMFYUI_DIR" ]; then
  log "cloning ComfyUI"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$COMFYUI_DIR"
fi

# --- Python environment ----------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
  log "creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$COMFYUI_DIR/requirements.txt"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# --- MiniMax-H3 custom nodes ------------------------------------------------
# Install the custom-node pack that provides the Ref2VA/MiniMax-H3 workflow
# nodes. Pin a known-good revision in production.
# git clone <custom-node-repo> "$COMFYUI_DIR/custom_nodes/ref2va_h3"
# pip install -r "$COMFYUI_DIR/custom_nodes/ref2va_h3/requirements.txt"

# --- Weights ---------------------------------------------------------------
mkdir -p "$MODELS_DIR"
log "download MiniMax-H3 weights into $MODELS_DIR (~90 GB)"
log "NOTE: fetch from the upstream model source and comply with its license."
# Example:
#   huggingface-cli download <upstream-repo> --local-dir "$MODELS_DIR/minimax-h3"

log "done. Start a worker with: ./run_worker.sh --gpu <index> --port <port>"
