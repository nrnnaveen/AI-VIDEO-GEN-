"""
FastAPI backend — text → frames → MP4
"""
import gc
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import queue
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from PIL import Image
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aivid")

# ─── Pipeline management ───────────────────────────────────────────────────

_pipe = None
_pipe_lock = threading.Lock()


def _free_memory():
    """Release Python objects and GPU cache."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def get_pipe():
    """Lazy-load the diffusion pipeline with memory-efficient settings."""
    global _pipe
    with _pipe_lock:
        if _pipe is None:
            from diffusers import StableDiffusionPipeline
            model_id = os.getenv("SD_MODEL", "runwayml/stable-diffusion-v1-5")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            logger.info("Loading pipeline %s on %s (dtype=%s)", model_id, device, dtype)
            _pipe = StableDiffusionPipeline.from_pretrained(
                model_id,
                torch_dtype=dtype,
                safety_checker=None,
                requires_safety_checker=False,
                low_cpu_mem_usage=True,
            ).to(device)
            # Always enable memory-saving features regardless of device
            _pipe.enable_attention_slicing(1)
            try:
                _pipe.enable_vae_slicing()
            except AttributeError:
                pass  # older diffusers versions may not have this
            logger.info("✔ Pipeline loaded on %s", device)
    return _pipe


def reset_pipe():
    """Unload the pipeline to reclaim memory (called after OOM)."""
    global _pipe
    with _pipe_lock:
        if _pipe is not None:
            logger.warning("Unloading pipeline to recover from OOM")
            del _pipe
            _pipe = None
    _free_memory()


# ─── App ───────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Video Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Content-Disposition", "X-Job-Id"],
)

OUTPUT_DIR = Path(tempfile.gettempdir()) / "aivid_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_JOB_CLEANUP_DELAY = 600.0   # seconds until completed job files are removed
_JOB_TIMEOUT       = 600.0   # seconds before an in-flight job is force-failed

# ─── Background job queue ──────────────────────────────────────────────────

# jobs: job_id -> {
#   "status":     "queued"|"processing"|"done"|"failed",
#   "video_path": str|None,
#   "error":      str|None,
#   "started_at": float|None,   # epoch seconds when processing began
# }
jobs: dict = {}
_jobs_lock  = threading.Lock()
_job_queue: queue.Queue = queue.Queue()

# Reference to the active worker thread (replaced by watchdog on crash)
_worker_thread: threading.Thread | None = None


def _cleanup_job(job_id: str, delay: float = _JOB_CLEANUP_DELAY):
    """Schedule removal of a job's output files after *delay* seconds."""
    def _remove():
        with _jobs_lock:
            job = jobs.pop(job_id, None)
        if job and job.get("video_path"):
            shutil.rmtree(Path(job["video_path"]).parent, ignore_errors=True)
    t = threading.Timer(delay, _remove)
    t.daemon = True
    t.start()


def _fail_job(job_id: str, reason: str, work_dir: Optional[Path] = None):
    """Mark job as failed, clean up its working directory, and log."""
    logger.error("[%s] FAILED — %s", job_id, reason)
    if work_dir is not None:
        shutil.rmtree(work_dir, ignore_errors=True)
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"]  = reason
    _cleanup_job(job_id, delay=60.0)  # keep error status visible briefly


def _worker():
    """
    Single background thread that processes jobs one at a time.

    Designed to be completely isolated from the Uvicorn main thread:
    all exceptions — including BaseException subclasses — are caught so
    the loop never exits accidentally and the server stays alive.
    """
    logger.info("Worker thread ready")
    while True:
        try:
            # Block until a job arrives; timeout lets us stay responsive
            try:
                job_id, req = _job_queue.get(timeout=5)
            except queue.Empty:
                continue

            logger.info("[%s] dequeued — prompt=%r", job_id, req.prompt[:80])
            t0 = time.time()

            with _jobs_lock:
                jobs[job_id]["status"]     = "processing"
                jobs[job_id]["started_at"] = t0

            work_dir = OUTPUT_DIR / job_id
            work_dir.mkdir(parents=True, exist_ok=True)

            try:
                logger.info("[%s] generating %d frames …", job_id, req.num_frames)
                generate_frames(req, work_dir)

                out_video = work_dir / "output.mp4"
                logger.info("[%s] assembling video …", job_id)
                frames_to_video(work_dir, out_video, req.fps)

                elapsed = time.time() - t0
                with _jobs_lock:
                    jobs[job_id]["status"]     = "done"
                    jobs[job_id]["video_path"] = str(out_video)
                logger.info("[%s] ✔ done in %.1fs → %s", job_id, elapsed, out_video)
                _cleanup_job(job_id)

            except torch.cuda.OutOfMemoryError as oom:
                logger.exception("[%s] OOM — resetting pipeline", job_id)
                reset_pipe()
                _fail_job(job_id, f"Out of memory: {oom}", work_dir)

            except Exception as exc:
                logger.exception("[%s] generation error: %s", job_id, exc)
                _free_memory()
                _fail_job(job_id, str(exc), work_dir)

            finally:
                _job_queue.task_done()
                _free_memory()

        except BaseException as fatal:
            # Catch SystemExit / KeyboardInterrupt / anything else so the
            # thread loop never exits and the server stays running.
            logger.exception("Worker caught fatal exception — continuing: %s", fatal)
            _free_memory()


def _start_worker() -> threading.Thread:
    """Spawn a new worker daemon thread and return it."""
    global _worker_thread
    t = threading.Thread(target=_worker, daemon=True, name="job-worker")
    t.start()
    _worker_thread = t
    logger.info("✔ Background worker thread started (tid=%s)", t.ident)
    return t


def _watchdog():
    """
    Monitor the worker thread and the job queue.

    Responsibilities:
    1. Restart the worker if it has died unexpectedly.
    2. Force-fail jobs that have been processing for longer than _JOB_TIMEOUT.
    """
    logger.info("✔ Watchdog thread started")
    while True:
        time.sleep(10)
        try:
            # ── Restart dead worker ──────────────────────────────────────
            if _worker_thread is None or not _worker_thread.is_alive():
                logger.warning("Worker thread is dead — restarting …")
                _start_worker()

            # ── Enforce job timeout ──────────────────────────────────────
            now = time.time()
            with _jobs_lock:
                timed_out = [
                    jid for jid, j in jobs.items()
                    if j["status"] == "processing"
                    and j.get("started_at") is not None
                    and (now - j["started_at"]) > _JOB_TIMEOUT
                ]
            for jid in timed_out:
                logger.warning("[%s] exceeded %ds timeout — marking failed", jid, int(_JOB_TIMEOUT))
                work_dir = OUTPUT_DIR / jid
                _fail_job(jid, f"Timed out after {int(_JOB_TIMEOUT)}s", work_dir)

        except Exception:
            logger.exception("Watchdog loop error (ignored)")


# ─── Startup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    """Start the worker and watchdog daemon threads."""
    try:
        _start_worker()
    except Exception as exc:
        logger.error("Could not start worker thread: %s", exc)
    try:
        wd = threading.Thread(target=_watchdog, daemon=True, name="watchdog")
        wd.start()
        logger.info("✔ Watchdog thread started")
    except Exception as exc:
        logger.error("Could not start watchdog thread: %s", exc)


# ─── Schemas ───────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    negative_prompt: Optional[str] = "blurry, low quality, distorted, ugly"
    num_frames: int = Field(default=6, ge=4, le=8)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)
    num_inference_steps: int = Field(default=15, ge=5, le=50)  # lower default to save memory
    fps: int = Field(default=8, ge=4, le=24)


# ─── Frame generation ──────────────────────────────────────────────────────

def generate_frames(req: GenerateRequest, work_dir: Path) -> list[Path]:
    """Generate *num_frames* slightly varied images and save them as PNG."""
    pipe = get_pipe()
    frames: list[Path] = []

    # Use 384×384 instead of 512×512 — significantly less VRAM / RAM
    img_size = int(os.getenv("IMG_SIZE", "384"))

    for i in range(req.num_frames):
        logger.info("[%s] frame %d/%d …", work_dir.name, i + 1, req.num_frames)
        seed = hash(req.prompt + str(i)) % (2**32)
        generator = torch.manual_seed(seed)

        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            guidance_scale=req.guidance_scale,
            num_inference_steps=req.num_inference_steps,
            generator=generator,
            width=img_size,
            height=img_size,
        )
        img: Image.Image = result.images[0]

        # Free intermediate tensors as early as possible
        del result
        _free_memory()

        # Progressive zoom crop for cinematic motion
        zoom = 1.0 + (i / max(req.num_frames - 1, 1)) * 0.06
        w, h = img.size
        new_w, new_h = int(w / zoom), int(h / zoom)
        left = (w - new_w) // 2
        top  = (h - new_h) // 2
        img  = img.crop((left, top, left + new_w, top + new_h)).resize((w, h), Image.LANCZOS)

        path = work_dir / f"frame_{i:03d}.png"
        img.save(path)
        frames.append(path)

    return frames


def frames_to_video(frames_dir: Path, output_path: Path, fps: int):
    """Use ffmpeg to assemble frames into an MP4 with fade filter."""
    n_frames = len(list(frames_dir.glob("frame_*.png")))
    fade_out_start = max(0.0, n_frames / fps - 0.6)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%03d.png"),
        "-vf", (
            "scale=512:512,"          # upscale to 512 for playback
            "fade=t=in:st=0:d=0.5,"
            f"fade=t=out:st={fade_out_start:.2f}:d=0.4"
        ),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        "-movflags", "+faststart",    # web-optimised MP4 (plays before fully downloaded)
        str(output_path),
    ]
    logger.info("ffmpeg command: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {proc.stderr[-800:]}")
    logger.info("ffmpeg finished OK (%d bytes)", output_path.stat().st_size)


# ─── Routes ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Root health-check endpoint (used by Render and load-balancers)."""
    return {"status": "ok", "service": "AI Video Generator API"}


@app.get("/health")
def health():
    return {"status": "ok", "gpu": torch.cuda.is_available()}


@app.get("/status")
def status():
    """Worker and queue health — useful for monitoring and debugging."""
    worker_alive = _worker_thread is not None and _worker_thread.is_alive()
    with _jobs_lock:
        counts = {"queued": 0, "processing": 0, "done": 0, "failed": 0}
        for j in jobs.values():
            counts[j["status"]] = counts.get(j["status"], 0) + 1
    return {
        "worker_alive": worker_alive,
        "queue_depth": _job_queue.qsize(),
        "jobs": counts,
        "gpu_available": torch.cuda.is_available(),
    }


@app.post("/generate")
async def generate(req: GenerateRequest):
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        jobs[job_id] = {
            "status":     "queued",
            "video_path": None,
            "error":      None,
            "started_at": None,
        }
    _job_queue.put((job_id, req))
    logger.info("[%s] queued — prompt=%r", job_id, req.prompt[:80])
    return {"job_id": job_id, "status": "queued"}


@app.get("/result/{job_id}")
async def result(job_id: str):
    with _jobs_lock:
        job = jobs.get(job_id)
        if job is not None:
            job = dict(job)  # snapshot — don't hold lock while streaming
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": job.get("error") or "Generation failed"},
            media_type="application/json",
        )
    if job["status"] in ("queued", "processing"):
        elapsed = None
        if job.get("started_at"):
            elapsed = round(time.time() - job["started_at"], 1)
        return JSONResponse(
            content={"status": job["status"], "elapsed_seconds": elapsed},
            media_type="application/json",
        )
    # status == "done" — stream the video file
    video_path = job.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=410, detail="Video file no longer available")
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"aivid_{job_id}.mp4",
        headers={
            "X-Job-Id":    job_id,
            "Cache-Control": "no-store",
            "Accept-Ranges": "bytes",
        },
    )


# ─── Hugging Face Spaces compatibility wrapper ─────────────────────────────
# When deployed as a Gradio Space the `app` object is reused directly via
# the `app.py` shim — nothing extra needed here.
