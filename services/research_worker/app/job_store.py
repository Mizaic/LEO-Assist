"""Research job persistence store.

Atlas trace:
  DO: DO-38C2D850
  DI: DI-58988BF2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-38C2D850")

Stores ResearchJob state in Redis with JSON serialisation.
Mirrors the pattern used by the training worker for consistency.

Jobs have a lifecycle: queued -> running -> done | failed | cancelled.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from uuid import uuid4

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_JOB_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
_KEY_PREFIX = "research_job:"


@dataclass
class ResearchJob:
    """Represents a single research algorithm run."""

    job_id: str
    mission_id: str
    area: str
    period: str
    detail: str
    org_ids: List[str]
    is_admin: bool
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    patient_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise job to dict (safe for JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchJob":
        """Deserialise from dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ResearchJobStore:
    """Redis-backed store for research jobs."""

    def __init__(self) -> None:
        self._redis = redis.from_url(REDIS_URL, decode_responses=True)

    def create(
        self,
        mission_id: str,
        area: str,
        period: str,
        detail: str,
        org_ids: List[str],
        is_admin: bool,
        patient_id: Optional[str] = None,
    ) -> ResearchJob:
        """Create and persist a new job."""
        job = ResearchJob(
            job_id=f"RES_{uuid4().hex[:16]}",
            mission_id=mission_id,
            area=area,
            period=period,
            detail=detail,
            org_ids=org_ids,
            is_admin=is_admin,
            patient_id=patient_id,
        )
        self._save(job)
        return job

    def get(self, job_id: str) -> Optional[ResearchJob]:
        """Retrieve a job by ID."""
        raw = self._redis.get(f"{_KEY_PREFIX}{job_id}")
        if raw is None:
            return None
        try:
            return ResearchJob.from_dict(json.loads(raw))
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Failed to deserialise job %s: %s", job_id, exc)
            return None

    def update(self, job: ResearchJob, **kwargs: Any) -> ResearchJob:
        """Update job fields and persist."""
        for key, value in kwargs.items():
            if hasattr(job, key):
                object.__setattr__(job, key, value) if hasattr(
                    job, "__dataclass_fields__"
                ) else setattr(job, key, value)
                setattr(job, key, value)
        self._save(job)
        return job

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return up to `limit` most-recent jobs."""
        pattern = f"{_KEY_PREFIX}*"
        keys = list(self._redis.scan_iter(pattern, count=200))
        jobs = []
        for key in keys:
            raw = self._redis.get(key)
            if raw:
                try:
                    jobs.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    continue
        jobs.sort(key=lambda j: j.get("created_at", 0), reverse=True)
        return jobs[:limit]

    def _save(self, job: ResearchJob) -> None:
        """Persist a job to Redis with TTL."""
        key = f"{_KEY_PREFIX}{job.job_id}"
        self._redis.setex(key, _JOB_TTL_SECONDS, json.dumps(job.to_dict()))


def get_store() -> ResearchJobStore:
    """Return a ResearchJobStore instance (creates per-call, stateless)."""
    return ResearchJobStore()
