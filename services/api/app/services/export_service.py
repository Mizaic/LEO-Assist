"""Training and validation dataset export service."""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.neo4j_client import CodingGraphClient
from app.services.neo4j_store import list_approved_candidates


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ExportService:
    def __init__(self, neo4j_client: CodingGraphClient) -> None:
        self.neo4j = neo4j_client

    def create_export(self, export_name: str, train_ratio: float, seed: int) -> dict[str, Any]:
        with self.neo4j.session() as session:
            approved = list_approved_candidates(session=session)

        random.Random(seed).shuffle(approved)
        cutoff = int(len(approved) * train_ratio)
        train = approved[:cutoff]
        validation = approved[cutoff:]

        manifest = {
            "export_name": export_name,
            "exported_at": datetime.now(UTC).isoformat(),
            "approved_rows": len(approved),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "train_hash": _stable_hash(train),
            "validation_hash": _stable_hash(validation),
            "candidate_ids": [c.get("candidate_id") for c in approved],
        }
        return {
            "export_id": str(uuid.uuid4()),
            "approved_rows": len(approved),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "manifest": manifest,
        }
