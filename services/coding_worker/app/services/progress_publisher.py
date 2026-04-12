from __future__ import annotations

import json
import os


def _get_redis():
    from redis import from_url

    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return from_url(url)


def publish_progress(run_id: str, event: dict) -> None:
    try:
        client = _get_redis()
        payload = json.dumps(event)
        client.publish(f"pipeline:{run_id}", payload)
        # Keep the most recent event for late SSE subscribers.
        client.setex(f"pipeline:last:{run_id}", 3600, payload)
    except Exception:
        return
