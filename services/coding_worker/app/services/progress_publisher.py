from __future__ import annotations

import json


def _get_redis():
    from redis import from_url

    return from_url("redis://localhost:6379")


def publish_progress(run_id: str, event: dict) -> None:
    try:
        client = _get_redis()
        client.publish(f"pipeline:{run_id}", json.dumps(event))
    except Exception:
        return
