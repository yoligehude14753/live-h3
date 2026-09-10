#!/usr/bin/env python3
"""Three-lane Ref2VA/MiniMax-H3 orchestrator.

One ComfyUI worker per GPU. A job is one clip; the orchestrator renders it on a
single worker, and a batch shards clips across workers. A lane never blocks on a
bare Event waiting for its clip thread — it waits on the Future with the
remaining deadline, so a clip that crashes propagates immediately instead of
deadlocking the lane until the deadline.

This module is deployment-only: no story, voting, or scheduling logic.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .worker_client import (
    ReferenceUploadCache,
    execution_seconds,
    http_bytes,
    http_json,
    output_video,
    submit_and_wait_polling,
)


class OrchestratorError(RuntimeError):
    def __init__(self, message: str, *, results: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.results = results or []


def build_reference_workflow(profile: dict[str, Any], prompt: str, seed: int, prefix: str,
                             audio_files: list[str], image_files: list[str],
                             first_frame_file: str | None = None,
                             last_frame_file: str | None = None) -> dict[str, Any]:
    """Assemble the Ref2VA ComfyUI workflow. File names must already be uploaded
    to the target worker's input directory, in Picture/Audio tag order."""
    from .worker_client import build_workflow

    effective = {**profile,
                 "num_frames": int(profile["num_frames"]),
                 "fps": int(profile["native_fps"]),
                 "duration_seconds": int(profile["num_frames"]) / int(profile["native_fps"]),
                 "num_inference_steps": int(profile["num_inference_steps"])}
    workflow = build_workflow(effective, prompt, seed, prefix)
    workflow["138"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
        "model": ["134", 0], "shift_video": float(profile["shift_video"]),
        "shift_audio": float(profile["shift_audio"])}}
    workflow["124"]["inputs"]["model"] = ["127", 0]
    workflow["126"]["inputs"]["model"] = ["138", 0]
    inputs = workflow["131"]["inputs"]
    workflow["131"]["class_type"] = "MiniMaxH3ReferenceToVideo"
    inputs.update(audio_vae=["120", 0], ref_image_size=profile["ref_image_size"])
    for index, name in enumerate(audio_files):
        node = str(200 + index)
        workflow[node] = {"class_type": "LoadAudio", "inputs": {"audio": name}}
        inputs[f"ref_audios.ref_audio_{index}"] = [node, 0]
    for index, name in enumerate(image_files):
        node = str(220 + index)
        workflow[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
        inputs[f"ref_images.ref_image_{index}"] = [node, 0]
    positive = ["131", 0]
    if first_frame_file:
        workflow["240"] = {"class_type": "LoadImage", "inputs": {"image": first_frame_file}}
        workflow["241"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": positive, "vae": ["119", 0], "latent": ["131", 1],
            "image": ["240", 0], "frame_idx": 0}}
        positive = ["241", 0]
    if last_frame_file:
        workflow["242"] = {"class_type": "LoadImage", "inputs": {"image": last_frame_file}}
        workflow["243"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": positive, "vae": ["119", 0], "latent": ["131", 1],
            "image": ["242", 0], "frame_idx": -1}}
        positive = ["243", 0]
    workflow["126"]["inputs"]["conditioning"] = positive
    return workflow


class ThreeLaneOrchestrator:
    def __init__(self, config: dict[str, Any], runtime_root: Path):
        self.profile = dict(config["profile"])
        self.workers = [dict(w, lane_id=f"LANE_{i}") for i, w in enumerate(config["workers"])]
        self.runtime_root = Path(runtime_root)
        self.media_root = self.runtime_root / "media"
        self.raw_root = self.runtime_root / "raw"
        self.receipt_root = self.runtime_root / "receipts"
        for d in (self.media_root, self.raw_root, self.receipt_root):
            d.mkdir(parents=True, exist_ok=True)
        self.poll_interval = float(config.get("poll_interval_seconds", 0.2))
        self.cache = ReferenceUploadCache(self.runtime_root / "reference_uploads.json")
        self.lock = threading.RLock()
        self.active_prompt_ids: dict[str, set[str]] = {w["lane_id"]: set() for w in self.workers}

    # -- worker HTTP helpers -------------------------------------------------
    def _queue(self, worker: dict[str, Any]) -> dict[str, Any]:
        timeout = float(worker.get("health_timeout_seconds", 8))
        return http_json(worker["url"].rstrip("/") + "/queue", timeout=timeout)

    def _wait_idle(self, deadline: float) -> None:
        while True:
            states = []
            for w in self.workers:
                q = self._queue(w)
                states.append((len(q.get("queue_running") or []), len(q.get("queue_pending") or [])))
            if all(r == 0 and p == 0 for r, p in states):
                return
            if time.time() >= deadline:
                raise OrchestratorError(f"workers did not become IDLE before deadline: {states}")
            time.sleep(min(self.poll_interval, deadline - time.time()))

    def _uploaded(self, worker, bindings, kind):
        route = (worker.get("reference_upload_url") or worker["url"]).rstrip("/")
        return [self.cache.upload(route, kind, Path(b)) for b in bindings]

    # -- media validation / delivery -----------------------------------------
    def _probe(self, path: Path, *, delivery: bool) -> dict[str, Any]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
             "-of", "json", str(path)], capture_output=True, text=True, check=False)
        if probe.returncode:
            raise OrchestratorError("ffprobe failed: " + (probe.stderr or probe.stdout))
        payload = json.loads(probe.stdout)
        video = next((s for s in payload.get("streams") or [] if s.get("codec_type") == "video"), None)
        audio = next((s for s in payload.get("streams") or [] if s.get("codec_type") == "audio"), None)
        if not video:
            raise OrchestratorError("rendered media has no video stream")
        frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
        num, den = str(video.get("avg_frame_rate") or "0/1").split("/")[:2]
        fps = float(num) / float(den) if float(den) else 0.0
        expected = int(self.profile["fps" if delivery else "native_fps"])
        if frames != int(self.profile["num_frames"]) or abs(fps - expected) > 1e-6:
            raise OrchestratorError(f"media envelope mismatch frames={frames} fps={fps}")
        if delivery and (video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p"
                         or not audio or audio.get("codec_name") != "aac"):
            raise OrchestratorError("delivery media does not match H264/AAC envelope")
        return {"frames": frames, "fps": fps, "has_audio": audio is not None,
                "duration": float(video.get("duration") or payload.get("format", {}).get("duration") or 0)}

    def _transcode(self, source: Path, target: Path, deadline: float) -> float:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("deadline elapsed before delivery transcode")
        p = self.profile
        started = time.perf_counter()
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(source),
               "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", (f"setpts={int(p['native_fps'])}/{int(p['fps'])}*(PTS-STARTPTS),"
                       f"scale={int(p['delivery_width'])}:{int(p['delivery_height'])}:"
                       "force_original_aspect_ratio=decrease,"
                       f"pad={int(p['delivery_width'])}:{int(p['delivery_height'])}:(ow-iw)/2:(oh-ih)/2:color=black,"
                       f"fps={int(p['fps'])},format=yuv420p"),
               "-c:v", "libx264", "-preset", str(p.get("delivery_encoder_preset", "veryfast")),
               "-b:v", f"{int(p['delivery_video_bitrate_kbps'])}k",
               "-maxrate", f"{int(p['delivery_video_bitrate_kbps'])}k",
               "-bufsize", f"{int(p['delivery_video_bitrate_kbps']) * 2}k",
               "-g", str(int(p["delivery_gop_frames"])), "-keyint_min", str(int(p["delivery_gop_frames"])),
               "-sc_threshold", "0",
               "-af", f"atempo={int(p['fps']) / int(p['native_fps']):.12g},asetpts=PTS-STARTPTS",
               "-c:a", "aac", "-b:a", f"{int(p['delivery_audio_bitrate_kbps'])}k",
               "-t", str(float(p["duration_seconds"])), "-movflags", "+faststart", str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=remaining, check=False)
        if proc.returncode:
            raise OrchestratorError("delivery transcode failed: " + (proc.stderr or proc.stdout))
        return time.perf_counter() - started

    # -- one clip on one worker ----------------------------------------------
    def render_clip(self, worker: dict[str, Any], job: dict[str, Any], deadline: float) -> dict[str, Any]:
        lane_id = worker["lane_id"]
        started = time.perf_counter()
        prompt = job["prompt"]
        image_names = self._uploaded(worker, job.get("image_references", []), "image")
        audio_names = self._uploaded(worker, job.get("audio_references", []), "audio")
        first = self._uploaded(worker, [job["first_frame"]], "first-frame")[0] if job.get("first_frame") else None
        last = self._uploaded(worker, [job["last_frame"]], "last-frame")[0] if job.get("last_frame") else None
        seed = job.get("seed", uuid.uuid4().int % (1 << 63))
        prefix = f"ref2va/{uuid.uuid4().hex[:12]}"
        workflow = build_reference_workflow(self.profile, prompt, seed, prefix,
                                            audio_names, image_names, first, last)
        execution_url = (worker.get("execution_url") or worker["url"]).rstrip("/")
        timeout = deadline - time.time()
        if timeout <= 0:
            raise TimeoutError("deadline elapsed before dispatch")

        def remember(prompt_id: str) -> None:
            with self.lock:
                self.active_prompt_ids[lane_id].add(prompt_id)

        prompt_id, history = submit_and_wait_polling(
            execution_url, {"prompt": workflow, "client_id": f"ref2va-{uuid.uuid4().hex}"},
            headers={}, timeout=timeout,
            submit_timeout_seconds=float(worker.get("submit_timeout_seconds", 15)),
            history_read_timeout_seconds=float(worker.get("history_read_timeout_seconds", 8)),
            prompt_started=remember, poll_interval_seconds=self.poll_interval)
        descriptor = output_video(history, prompt_id)
        if descriptor is None:
            raise OrchestratorError(f"{worker['id']} completed without an MP4")
        query = urllib.parse.urlencode({"filename": descriptor["filename"],
                                        "subfolder": descriptor.get("subfolder", ""),
                                        "type": descriptor.get("type", "output")})
        raw = self.raw_root / f"{uuid.uuid4().hex[:12]}.mp4"
        final = self.media_root / f"{job.get('name', 'clip')}-{uuid.uuid4().hex[:8]}.mp4"
        media_bytes = None
        for attempt in range(3):
            dl_timeout = deadline - time.time()
            if dl_timeout <= 0:
                raise TimeoutError("deadline elapsed before media download")
            media_bytes = http_bytes(execution_url + "/view?" + query, timeout=dl_timeout)
            raw.write_bytes(media_bytes)
            try:
                self._probe(raw, delivery=False)
                break
            except OrchestratorError:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        self._transcode(raw, final, deadline)
        raw.unlink()
        media = self._probe(final, delivery=True)
        if time.time() > deadline:
            raise TimeoutError("complete media arrived after deadline")
        return {"worker_id": worker["id"], "lane_id": lane_id, "prompt_id": prompt_id,
                "media": str(final), "wall_seconds": round(time.perf_counter() - started, 3),
                "execution_seconds": execution_seconds(history, prompt_id),
                "envelope": media}

    # -- a batch sharded across lanes -----------------------------------------
    def render_batch(self, jobs: list[dict[str, Any]], deadline: float) -> dict[str, Any]:
        if len(jobs) > len(self.workers):
            raise OrchestratorError(f"batch of {len(jobs)} exceeds {len(self.workers)} workers")
        self._wait_idle(deadline)
        started = time.perf_counter()
        pool = ThreadPoolExecutor(max_workers=len(self.workers), thread_name_prefix="ref2va-lane")
        futures = {pool.submit(self.render_clip, self.workers[i], job, deadline): i
                   for i, job in enumerate(jobs)}
        results, failure = [], None
        try:
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    failure = exc
                    break
        finally:
            pool.shutdown(wait=failure is None, cancel_futures=failure is not None)
        if failure:
            raise OrchestratorError(f"batch failed: {type(failure).__name__}: {failure}", results=results)
        wall = time.perf_counter() - started
        receipt = {"wall_seconds": round(wall, 3),
                   "rtf": round(wall / float(self.profile["duration_seconds"]), 4),
                   "clips": sorted(results, key=lambda r: r["lane_id"])}
        (self.receipt_root / f"receipt-{uuid.uuid4().hex[:12]}.json").write_text(
            json.dumps(receipt, indent=2) + "\n")
        return receipt
