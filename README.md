# Image Moderation Service

A small, stateless HTTP service that measures an image with several detectors, applies one shared
policy (`policy.py`) and returns an **allow / review / reject** verdict with the raw signals behind
it. Callers decide how to act on a verdict (refuse, hold for review, or only record it).
Images are never written to disk or logged.

| Detector | What it returns | License |
|---|---|---|
| OpenAI `omni-moderation-latest` | flagged, per-category booleans and scores | API terms (free endpoint) |
| GantMan nsfw_model (mobilenet_v2_140_224, 1.2.0) | drawings / hentai / neutral / porn / sexy probabilities | MIT |
| NudeNet 320n (3.4.2) | body-part detections (exposed / covered) | AGPL-3.0 |

Because NudeNet is AGPL-3.0, this service is licensed AGPL-3.0 (see `LICENSE`). Callers talk to it
only over HTTP.

## API

- `GET /health` — no auth; status and whether OpenAI is configured.
- `POST /v1/analyze` — header `X-Api-Key`, body = raw image bytes (JPEG/PNG/WebP/GIF, ≤ 20 MB).
  Returns `verdict` (`allow`/`review`/`reject`), `reasons`, `policy_version`, the raw `openai`,
  `gantman` and `nudenet` signals, `models`, `caller` and `elapsed_ms`.
  `401` bad key · `413` too large · `415` not an image · `503` a detector failed (callers should fail closed).

## Configuration

| Variable | |
|---|---|
| `OPENAI_API_KEY` | required |
| `MODERATION_CLIENT_KEYS` | required; `name=key` pairs, comma-separated, one per caller |
| `MODERATION_GANTMAN_EXPLICIT` | optional policy threshold (default 0.70) |
| `MODERATION_NUDENET_EXPLICIT` | optional policy threshold (default 0.50) |

Run bound to localhost: `uvicorn app:app --host 127.0.0.1 --port 5390`, or in production
`python run_service.py <secrets.json>` (loads the variables above from a JSON file readable only by the
service account).

Policy tests: `python -m unittest`
