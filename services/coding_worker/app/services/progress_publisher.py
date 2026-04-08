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
        client.publish(f"pipeline:{run_id}", json.dumps(event))
    except Exception:
        return
