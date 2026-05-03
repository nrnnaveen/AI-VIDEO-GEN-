"""
FastAPI backend — text → frames → MP4
"""
import os, uuid, shutil, subprocess, tempfile, threading, queue
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image
import torch

# ─── Lazy-load pipeline to avoid cold-start crash on CPU ───────────────────
_pipe = None

def get_pipe():
    global _pipe
    if _pipe is None:
        from diffusers import StableDiffusionPipeline
        model_id = os.getenv("SD_MODEL", "runwayml/stable-diffusion-v1-5")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        _pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            safety_checker=None,          # disable for speed
            requires_safety_checker=False,
        ).to(device)
        if device == "cpu":
            _pipe.enable_attention_slicing()
        print(f"✔ Pipeline loaded on {device}")
    return _pipe


app = FastAPI(title="AI Video Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(tempfile.gettempdir()) / "aivid_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_JOB_CLEANUP_DELAY = 600.0  # seconds until completed job files are removed

# ─── Background job queue ──────────────────────────────────────────────────

# jobs: job_id -> {"status": "queued"|"processing"|"done"|"failed",
#                  "video_path": str|None, "error": str|None}
jobs: dict = {}
_jobs_lock = threading.Lock()
_job_queue: queue.Queue = queue.Queue()


def _cleanup_job(job_id: str, delay: float = _JOB_CLEANUP_DELAY):
    """Schedule removal of a job and its output files after `delay` seconds."""
    def _remove():
        with _jobs_lock:
            job = jobs.pop(job_id, None)
        if job and job.get("video_path"):
            shutil.rmtree(Path(job["video_path"]).parent, ignore_errors=True)
    t = threading.Timer(delay, _remove)
    t.daemon = True
    t.start()


def _worker():
    """Single background thread that processes jobs one at a time."""
    while True:
        job_id, req = _job_queue.get()
        with _jobs_lock:
            jobs[job_id]["status"] = "processing"
        work_dir = OUTPUT_DIR / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            generate_frames(req, work_dir)
            out_video = work_dir / "output.mp4"
            frames_to_video(work_dir, out_video, req.fps)
            with _jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["video_path"] = str(out_video)
            _cleanup_job(job_id)
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            with _jobs_lock:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = str(exc)
            _cleanup_job(job_id)
        finally:
            _job_queue.task_done()


@app.on_event("startup")
async def _startup():
    """Start the background job-worker thread after the server has bound its port."""
    try:
        t = threading.Thread(target=_worker, daemon=True, name="job-worker")
        t.start()
        print("✔ Background worker thread started")
    except Exception as exc:
        print(f"WARNING: could not start worker thread: {exc}")


# ─── Schemas ───────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    negative_prompt: Optional[str] = "blurry, low quality, distorted, ugly"
    num_frames: int = Field(default=6, ge=4, le=8)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)
    num_inference_steps: int = Field(default=25, ge=10, le=50)
    fps: int = Field(default=8, ge=4, le=24)


# ─── Frame generation ──────────────────────────────────────────────────────

def generate_frames(req: GenerateRequest, work_dir: Path) -> list[Path]:
    """Generate `num_frames` slightly varied images and save as PNG."""
    pipe = get_pipe()
    frames: list[Path] = []

    # Subtle zoom progression: scale 1.0 → 1.06 across frames
    for i in range(req.num_frames):
        seed = hash(req.prompt + str(i)) % (2**32)
        generator = torch.manual_seed(seed)

        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            guidance_scale=req.guidance_scale,
            num_inference_steps=req.num_inference_steps,
            generator=generator,
            width=512,
            height=512,
        )
        img: Image.Image = result.images[0]

        # Apply progressive zoom crop for cinematic motion
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
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%03d.png"),
        "-vf", (
            "scale=512:512,"
            "fade=t=in:st=0:d=0.5,"
            f"fade=t=out:st={max(0, len(list(frames_dir.glob('*.png'))) / fps - 0.6):.2f}:d=0.4"
        ),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-600:]}")


# ─── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "gpu": torch.cuda.is_available()}


@app.post("/generate")
async def generate(req: GenerateRequest):
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        jobs[job_id] = {"status": "queued", "video_path": None, "error": None}
    _job_queue.put((job_id, req))
    return {"job_id": job_id, "status": "queued"}


@app.get("/result/{job_id}")
async def result(job_id: str):
    with _jobs_lock:
        job = jobs.get(job_id)
        if job is not None:
            job = dict(job)  # snapshot to avoid holding the lock while streaming
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == "failed":
        return {"status": "failed", "error": job.get("error") or "Generation failed"}
    if job["status"] in ("queued", "processing"):
        return {"status": job["status"]}
    # done — stream the video file
    return FileResponse(
        path=str(job["video_path"]),
        media_type="video/mp4",
        filename=f"aivid_{job_id}.mp4",
        headers={"X-Job-Id": job_id},
    )


# ─── Hugging Face Spaces compatibility wrapper ─────────────────────────────
# When deployed as a Gradio Space the `app` object is reused directly via
# the `app.py` shim — nothing extra needed here.
