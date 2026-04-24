"""Active learning review queue.

Atlas trace:
  DO: DO-A00CD165
  DI: DI-3FDBB57B

When inference emits a span whose raw confidence falls in the "grey zone"
(between :data:`REVIEW_LOWER_BOUND` and the per-label threshold), that span is
a useful training candidate. Rather than dropping it silently, we enqueue it
for human review. Curators in the UI can accept, reject, or relabel — those
decisions become new GoldLabel records.

Two backends are supported:

* ``file`` (default) — JSON Lines appended to ``REVIEW_QUEUE_DIR``.
* ``neo4j`` — creates a ``:ReviewItem`` node and a ``REVIEW_PENDING``
  relationship to the originating sentence when ``REVIEW_QUEUE_BACKEND=neo4j``.

Never retains raw patient text beyond the span surface form; the ingesting
component is expected to replace PHI before calling :func:`enqueue`.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class ReviewItem:
    """One review candidate — the curator UI renders these as cards."""

    model_version: str
    label: str
    start_char: int
    end_char: int
    surface: str
    raw_score: float
    calibrated_score: float
    sentence_id: str = ""
    context_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    reason: str = "below_threshold"

    def to_dict(self) -> dict:
        return asdict(self)


class ReviewQueue:
    """File-based review queue (default).

    Thread-safe but deliberately simple. Production installs should migrate to
    the Neo4j backend.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._base_dir = Path(
            base_dir or os.getenv("REVIEW_QUEUE_DIR", "/var/lib/leo/review_queue")
        )
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, items: Iterable[ReviewItem]) -> int:
        count = 0
        try:
            path = self._path_for_today()
            with self._lock, path.open("a", encoding="utf-8") as fh:
                for item in items:
                    fh.write(json.dumps(item.to_dict(), ensure_ascii=False))
                    fh.write("\n")
                    count += 1
        except Exception as exc:
            logger.warning("[review-queue] enqueue failed (%s) — dropping batch", exc)
        return count

    def _path_for_today(self) -> Path:
        day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        return self._base_dir / f"review-{day}.jsonl"


def should_enqueue(raw_score: float, threshold: float, lower_bound: float = 0.4) -> bool:
    """Return True when ``raw_score`` is in the review band.

    Inside ``[lower_bound, threshold)``: below the live threshold but close
    enough to be worth a curator's attention.
    """
    return lower_bound <= raw_score < threshold
