#!/usr/bin/env bash
# Install ComfyUI + Python deps for a Ref2VA/MiniMax-H3 worker. Idempotent.
set -euo pipefail
VENV_DIR="${VENV_DIR:-./.venv}"
COMFYUI_DIR="${COMFYUI_DIR:-./ComfyUI}"
MODELS_DIR="${MODELS_DIR:-./models}"

command -v python3 >/dev/null || { echo "python3 >= 3.10 required"; exit 1; }
command -v git >/dev/null || { echo "git required"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "NVIDIA driver not found"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg required (delivery transcode)"; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe required (media validation)"; exit 1; }

echo "[setup] GPUs on this host:"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader

[ -d "$COMFYUI_DIR" ] || git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$COMFYUI_DIR"

[ -d "$VENV_DIR" ] || python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r "$COMFYUI_DIR/requirements.txt"
pip install requests aiohttp

# MiniMax-H3 custom nodes provide: MiniMaxH3ReferenceToVideo, MiniMaxH3ImageToVideo,
# MiniMaxH3SigmaShift, MiniMaxH3AddGuide, SaveVideo, CreateVideo, VAEDecodeAudio,
# AudioAdjustVolume. Install the node pack that ships these class types.
#   git clone <minimax-h3-comfyui-nodes> "$COMFYUI_DIR/custom_nodes/minimax_h3"

echo "[setup] download MiniMax-H3 weights into $MODELS_DIR (see docs/hardware.md)."
echo "[setup] required files (from config profile):"
echo "  unet:          minimax_h3_ref2va_pruned_int8_convrot.safetensors"
echo "  lora:          minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
echo "  text_encoder:  qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
echo "  video_vae:     minimax_h3_video_vae_fp16.safetensors"
echo "  audio_vae:     minimax_h3_audio_vae_fp32.safetensors"
echo "[setup] done. Start a worker: ./run_worker.sh --gpu <index> --port <port>"
