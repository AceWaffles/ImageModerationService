"""Production launcher: load secrets from a JSON file into the environment, then serve on localhost.

    python run_service.py <secrets.json> [port]

The secrets file holds OPENAI_API_KEY and MODERATION_CLIENT_KEYS (and optionally the policy
thresholds). Keep it readable only by the account the service runs as.
"""
import json
import os
import sys

import uvicorn

if len(sys.argv) < 2:
    sys.exit("usage: python run_service.py <secrets.json> [port]")
with open(sys.argv[1], encoding="utf-8") as f:
    os.environ.update({k: str(v) for k, v in json.load(f).items()})

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)
uvicorn.run("app:app", host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv) > 2 else 5390, log_level="warning")
