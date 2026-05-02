"""
Hugging Face Spaces entry point.
Gradio mounts the FastAPI app automatically when a `app` variable is
an ASGI application.  This thin shim exposes it.
"""
from main import app   # noqa: F401  – HF Spaces picks up `app`
