"""Image moderation service: measures an image with every detector, applies the shared policy
(policy.py) and returns the verdict with the raw signals behind it.

Callers decide what to do with a verdict (refuse, hold for review, or only record it).
Stateless: images are never written to disk or logged.

Detectors
  openai   OpenAI omni-moderation-latest (free endpoint; needs OPENAI_API_KEY)
  gantman  GantMan nsfw_model mobilenet_v2_140_224 (MIT): drawings/hentai/neutral/porn/sexy
  nudenet  NudeNet 320n (AGPL-3.0): exposed/covered body-part detections

Environment
  OPENAI_API_KEY           required
  MODERATION_CLIENT_KEYS   required; comma-separated name=key pairs, one per caller
                           (e.g. production=...,staging=...)
"""
import asyncio
import base64
import hmac
import io
import os
import threading
import time

import httpx
import numpy as np
from ai_edge_litert.interpreter import Interpreter
from fastapi import FastAPI, HTTPException, Request
from nudenet import NudeDetector
from PIL import Image, ImageOps, UnidentifiedImageError

import policy

SERVICE_VERSION = "1.1.0"
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 50_000_000
OPENAI_MODEL = "omni-moderation-latest"
GANTMAN_MODEL = "gantman-mobilenet_v2_140_224-1.2.0"
GANTMAN_LABELS = ["drawings", "hentai", "neutral", "porn", "sexy"]
NUDENET_MODEL = "nudenet-320n-3.4"

_here = os.path.dirname(os.path.abspath(__file__))
_gantman = Interpreter(model_path=os.path.join(_here, "models", "gantman_mobilenet_v2_140_224.tflite"))
_gantman.allocate_tensors()
_gantman_lock = threading.Lock()  # a TFLite interpreter is not thread-safe
_nudenet = NudeDetector()


def _client_keys() -> dict[str, str]:
    pairs = (p.split("=", 1) for p in os.environ.get("MODERATION_CLIENT_KEYS", "").split(",") if "=" in p)
    return {name.strip(): key.strip() for name, key in pairs if key.strip()}


def _authenticate(request: Request) -> str:
    supplied = request.headers.get("x-api-key", "")
    for name, key in _client_keys().items():
        if hmac.compare_digest(supplied.encode(), key.encode()):
            return name
    raise HTTPException(401, "Invalid or missing API key.")


def _gantman_scores(image: Image.Image) -> dict[str, float]:
    # Matches the model's own predict.py: nearest-neighbour resize to 224, scale to 0..1.
    tensor = (np.asarray(image.resize((224, 224), Image.NEAREST), np.float32) / 255.0)[None]
    with _gantman_lock:
        _gantman.set_tensor(_gantman.get_input_details()[0]["index"], tensor)
        _gantman.invoke()
        scores = _gantman.get_tensor(_gantman.get_output_details()[0]["index"])[0]
    return {label: round(float(s), 4) for label, s in zip(GANTMAN_LABELS, scores)}


def _nudenet_detections(jpeg: bytes) -> list[dict]:
    return [{"class": d["class"], "score": round(float(d["score"]), 4)} for d in _nudenet.detect(jpeg)]


async def _openai(jpeg: bytes) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    body = {"model": OPENAI_MODEL, "input": [{"type": "image_url", "image_url": {
        "url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}]}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.openai.com/v1/moderations", json=body,
                                     headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    result = response.json()["results"][0]
    return {"model": OPENAI_MODEL, "flagged": result["flagged"],
            "categories": result["categories"],
            "scores": {k: round(v, 4) for k, v in result["category_scores"].items()}}


app = FastAPI(title="Image Moderation Service", version=SERVICE_VERSION, docs_url=None, redoc_url=None)


@app.get("/health")
def health():
    return {"status": "ok", "version": SERVICE_VERSION, "policy_version": policy.POLICY_VERSION,
            "clients": len(_client_keys()),
            "openai_configured": bool(os.environ.get("OPENAI_API_KEY"))}


@app.post("/v1/analyze")
async def analyze(request: Request):
    """Body: the raw image bytes (JPEG, PNG, WebP or GIF)."""
    caller = _authenticate(request)
    data = await request.body()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Image must be between 1 byte and 20 MB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise HTTPException(413, "Image dimensions are too large.")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "The file is not a supported image.")
    image.thumbnail((2000, 2000))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    jpeg = buffer.getvalue()

    started = time.perf_counter()
    try:
        openai, gantman, nudenet = await asyncio.gather(
            _openai(jpeg),
            asyncio.to_thread(_gantman_scores, image),
            asyncio.to_thread(_nudenet_detections, jpeg))
    except Exception as ex:  # any missing signal fails the whole request: callers fail closed
        raise HTTPException(503, f"A detector is unavailable ({type(ex).__name__}).")
    verdict, reasons = policy.evaluate(openai, gantman, nudenet)
    return {"verdict": verdict, "reasons": reasons, "policy_version": policy.POLICY_VERSION,
            "service_version": SERVICE_VERSION, "caller": caller,
            "models": {"openai": OPENAI_MODEL, "gantman": GANTMAN_MODEL, "nudenet": NUDENET_MODEL},
            "openai": openai, "gantman": gantman, "nudenet": nudenet,
            "elapsed_ms": round((time.perf_counter() - started) * 1000)}
