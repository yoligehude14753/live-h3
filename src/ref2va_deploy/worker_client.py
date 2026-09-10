#!/usr/bin/env python3
"""ComfyUI H3 worker 的共享 HTTP/WebSocket、参考素材缓存与基础工作流传输。

由 orchestrator 导入；不单独启动。可选 aiohttp 用于 WebSocket 完成事件。
"""
from __future__ import annotations

import asyncio
import copy
import json
import mimetypes
import os
import re
import secrets
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)


def http_bytes(url: str, *, method: str = "GET", body: bytes | None = None,
               headers: dict[str, str] | None = None, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{method} {url} failed: {type(exc).__name__}: {exc}") from exc


def http_json(url: str, *, method: str = "GET", value: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None, timeout: float = 30) -> dict[str, Any]:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() if value is not None else None
    merged = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    payload = json.loads(http_bytes(url, method=method, body=body, headers=merged, timeout=timeout))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned non-object JSON")
    return payload


def session_json(session: Any, url: str, *, method: str = "GET", value: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None, timeout: float = 30) -> dict[str, Any]:
    try:
        response = session.request(method, url, json=value, headers=headers or {}, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"{method} {url} failed: {type(exc).__name__}: {exc}") from exc
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"{method} {url} returned HTTP {response.status_code}: {response.text[:1000]}")
    try:
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned non-object JSON")
    return payload


def http_json_first(candidates: list[tuple], *, timeout: float) -> dict[str, Any]:
    """Read one resource through equivalent routes and return the first valid response."""
    def read(candidate: tuple) -> dict[str, Any]:
        url, headers, *rest = candidate
        session = rest[0] if rest else None
        return (session_json(session, url, headers=headers, timeout=timeout)
                if session is not None else http_json(url, headers=headers, timeout=timeout))

    if len(candidates) == 1:
        return read(candidates[0])
    pool = ThreadPoolExecutor(max_workers=len(candidates), thread_name_prefix="h3-history-read")
    futures = {pool.submit(read, candidate): candidate[0] for candidate in candidates}
    errors = []
    try:
        for future in as_completed(futures):
            try:
                return future.result()
            except Exception as exc:
                errors.append(f"{futures[future]}:{type(exc).__name__}:{exc}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    raise RuntimeError("all equivalent history routes failed: " + ";".join(errors)[:800])


def worker_auth_headers(token_file: str | None) -> dict[str, str]:
    if not token_file:
        return {}
    path = Path(token_file).expanduser()
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("worker token file must be an owner-private regular file")
    token = path.read_text(encoding="utf-8").strip()
    if not token or any(character.isspace() for character in token):
        raise RuntimeError("worker token file is invalid")
    return {"Authorization": "Bearer " + token}


def submit_and_wait(worker_url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout: float,
                    prompt_started: callable | None = None) -> str:
    try:
        import aiohttp
    except ImportError as exc:
        raise RuntimeError("aiohttp is required for ComfyUI completion events") from exc

    async def run() -> str:
        parsed = urllib.parse.urlsplit(worker_url)
        ws_url = urllib.parse.urlunsplit((
            "wss" if parsed.scheme == "https" else "ws",
            parsed.netloc,
            parsed.path.rstrip("/") + "/ws",
            urllib.parse.urlencode({"clientId": payload["client_id"]}),
            "",
        ))
        client_timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=None)
        async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
            async with session.ws_connect(ws_url, heartbeat=15) as websocket:
                async with session.post(worker_url.rstrip("/") + "/prompt", json=payload) as response:
                    result = await response.json(content_type=None)
                    if response.status != 200:
                        raise RuntimeError(f"ComfyUI prompt returned HTTP {response.status}: {str(result)[:500]}")
                prompt_id = str(result.get("prompt_id") or "")
                if not prompt_id:
                    raise RuntimeError("ComfyUI prompt response omitted prompt_id")
                if prompt_started:
                    prompt_started(prompt_id)
                deadline = asyncio.get_running_loop().time() + timeout
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError(f"ComfyUI prompt {prompt_id} exceeded final deadline")
                    message = await asyncio.wait_for(websocket.receive(), timeout=remaining)
                    if message.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(message.data)
                        data = event.get("data") if isinstance(event, dict) else None
                        if not isinstance(data, dict) or str(data.get("prompt_id") or "") != prompt_id:
                            continue
                        event_type = str(event.get("type") or "")
                        if event_type in {"execution_error", "execution_interrupted"}:
                            raise RuntimeError(f"ComfyUI prompt {prompt_id} ended with {event_type}")
                        if event_type == "execution_success" or (event_type == "executing" and data.get("node") is None):
                            return prompt_id
                    elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        raise RuntimeError("ComfyUI completion websocket closed")

    return asyncio.run(run())


def submit_and_wait_polling(worker_url: str, payload: dict[str, Any], *, headers: dict[str, str],
                            timeout: float, submit_timeout_seconds: float,
                            history_read_timeout_seconds: float,
                            prompt_started: callable | None = None,
                            history_url: str | None = None,
                            history_headers: dict[str, str] | None = None,
                            alternate_history_routes: list[tuple[str, dict[str, str]]] | None = None,
                            http_session: Any | None = None,
                            poll_interval_seconds: float = 0.2) -> tuple[str, dict[str, Any]]:
    """Submit exactly once, then observe that same prompt ID through history until terminal."""
    endpoint = worker_url.rstrip("/") + "/prompt"
    response = (session_json(http_session, endpoint, method="POST", value=payload,
                             headers=headers, timeout=min(submit_timeout_seconds, timeout))
                if http_session is not None
                else http_json(endpoint, method="POST", value=payload,
                               headers=headers, timeout=min(submit_timeout_seconds, timeout)))
    prompt_id = str(response.get("prompt_id") or "")
    if not prompt_id:
        raise RuntimeError("ComfyUI prompt response omitted prompt_id")
    if prompt_started:
        prompt_started(prompt_id)
    deadline = time.monotonic() + timeout
    history_path = "/history/" + urllib.parse.quote(prompt_id, safe="")
    history_routes = [((history_url or worker_url).rstrip("/") + history_path,
                       history_headers if history_headers is not None else headers, http_session)]
    history_routes.extend((base.rstrip("/") + history_path, route_headers)
                          for base, route_headers in (alternate_history_routes or []))
    while time.monotonic() < deadline:
        try:
            history = http_json_first(
                history_routes,
                timeout=min(history_read_timeout_seconds, deadline - time.monotonic()))
        except RuntimeError:
            time.sleep(min(max(0.05, poll_interval_seconds), max(0.05, deadline - time.monotonic())))
            continue
        item = history.get(prompt_id)
        if isinstance(item, dict):
            status = item.get("status") or {}
            status_name = str(status.get("status_str") or "").lower()
            messages = status.get("messages") or []
            if status_name in {"error", "failed"} or any(row and row[0] == "execution_error" for row in messages):
                raise RuntimeError(f"ComfyUI prompt {prompt_id} failed")
            if status.get("completed") or status_name == "success" or any(
                    row and row[0] == "execution_success" for row in messages):
                return prompt_id, history
        time.sleep(min(max(0.05, poll_interval_seconds), max(0.05, deadline - time.monotonic())))
    raise TimeoutError(f"ComfyUI prompt {prompt_id} exceeded final deadline")


def upload_input(route: str, kind: str, path: Path, remote_name: str,
                 *, timeout: float = 120, headers: dict[str, str] | None = None) -> str:
    boundary = f"----ref2va{secrets.token_hex(12)}"
    content = path.read_bytes()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{remote_name}\"\r\nContent-Type: {media_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput".encode(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue".encode(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    result = json.loads(http_bytes(
        route.rstrip("/") + "/upload/image",
        method="POST",
        body=b"".join(parts),
        headers={**(headers or {}), "Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=timeout,
    ))
    name = str(result.get("name") or "").strip()
    if not name:
        raise RuntimeError(f"worker did not return uploaded {kind} name")
    return name


class ReferenceUploadCache:
    def __init__(self, path: Path, seed_path: Path | None = None):
        self.path = Path(path)
        if self.path.exists():
            self.entries = json.loads(self.path.read_text(encoding="utf-8"))
        elif seed_path and Path(seed_path).is_file():
            self.entries = json.loads(Path(seed_path).read_text(encoding="utf-8"))
            atomic_json(self.path, self.entries)
        else:
            self.entries = {}
        self.lock = threading.Lock()
        self.asset_locks: dict[str, threading.Lock] = {}

    def upload(self, route: str, kind: str, path: Path, headers: dict[str, str] | None = None,
               *, allow_upload: bool = True) -> str:
        route = route.rstrip("/")
        path = Path(path)
        key = json.dumps([route, kind, str(path.resolve())], separators=(",", ":"))
        with self.lock:
            asset_lock = self.asset_locks.setdefault(key, threading.Lock())
        with asset_lock:
            with self.lock:
                cached = copy.deepcopy(self.entries.get(key))
            if cached:
                return str(cached["remote_name"])
            if not allow_upload:
                raise RuntimeError(f"reference cache miss for {route} {kind} {path.name}; runtime upload is disabled")
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name)
            remote_name = upload_input(route, kind, path, f"ref2va-{kind}-{safe}", headers=headers)
            with self.lock:
                self.entries[key] = {"route": route, "kind": kind, "source": str(path.resolve()),
                                     "remote_name": remote_name}
                atomic_json(self.path, self.entries)
            return remote_name


def build_workflow(profile: dict[str, Any], prompt: str, seed: int, prefix: str) -> dict[str, Any]:
    latent = {
        "clip": ["128", 0], "vae": ["119", 0], "prompt": prompt,
        "width": profile["source_width"], "height": profile["source_height"], "length": profile["num_frames"],
    }
    return {
        "92": {"class_type": "SaveVideo", "inputs": {"codec": "auto", "filename_prefix": prefix, "format": "auto", "video": ["130", 0]}},
        "119": {"class_type": "VAELoader", "inputs": {"vae_name": profile["video_vae"]}},
        "120": {"class_type": "VAELoader", "inputs": {"vae_name": profile["audio_vae"]}},
        "121": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["125", 0], "vae": ["120", 0]}},
        "122": {"class_type": "VAEDecode", "inputs": {"samples": ["125", 0], "vae": ["119", 0]}},
        "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": profile["sampler"]}},
        "124": {"class_type": "BasicScheduler", "inputs": {"denoise": 1.0, "model": ["134", 0], "scheduler": profile["scheduler"], "steps": profile["num_inference_steps"]}},
        "125": {"class_type": "SamplerCustomAdvanced", "inputs": {"guider": ["126", 0], "latent_image": ["131", 1], "noise": ["129", 0], "sampler": ["123", 0], "sigmas": ["124", 0]}},
        "126": {"class_type": "BasicGuider", "inputs": {"conditioning": ["131", 0], "model": ["134", 0]}},
        "127": {"class_type": "UNETLoader", "inputs": {"unet_name": profile["unet"], "weight_dtype": "default"}},
        "128": {"class_type": "CLIPLoader", "inputs": {"clip_name": profile["text_encoder"], "device": "default", "type": "minimax"}},
        "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "130": {"class_type": "CreateVideo", "inputs": {"audio": ["132", 0], "bit_depth": 8, "color_space": "sRGB", "fps": float(profile["fps"]), "images": ["122", 0]}},
        "131": {"class_type": "MiniMaxH3ImageToVideo", "inputs": latent},
        "132": {"class_type": "AudioAdjustVolume", "inputs": {"audio": ["121", 0], "volume": profile["audio_gain_db"]}},
        "134": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": profile["lora"], "model": ["127", 0], "strength_model": 1.0}},
    }


def output_video(history: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    item = history.get(prompt_id)
    if not isinstance(item, dict):
        return None
    status = item.get("status") or {}
    status_str = str(status.get("status_str") or "").lower()
    messages = status.get("messages") or []
    if status_str in {"error", "failed"} or any(row and row[0] == "execution_error" for row in messages):
        raise RuntimeError(f"ComfyUI prompt {prompt_id} failed: {json.dumps(status, ensure_ascii=False)[:800]}")
    for node in (item.get("outputs") or {}).values():
        if not isinstance(node, dict):
            continue
        for group in ("videos", "images", "gifs"):
            for descriptor in node.get(group) or []:
                if isinstance(descriptor, dict) and str(descriptor.get("filename", "")).lower().endswith(".mp4"):
                    return descriptor
    return None


def execution_seconds(history: dict[str, Any], prompt_id: str) -> float | None:
    item = history.get(prompt_id) or {}
    timestamps = {name: int(payload["timestamp"]) for name, payload in (item.get("status") or {}).get("messages") or []
                  if name in {"execution_start", "execution_success"} and "timestamp" in payload}
    if set(timestamps) != {"execution_start", "execution_success"}:
        return None
    return (timestamps["execution_success"] - timestamps["execution_start"]) / 1000
