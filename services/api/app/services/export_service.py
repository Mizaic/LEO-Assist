"""Training and validation dataset export service."""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.neo4j_client import PatientGraphClient
from app.services.neo4j_store import (
    list_approved_candidates,
    list_approved_candidates_for_patient,
)


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ExportService:
    def __init__(self, neo4j_client: PatientGraphClient) -> None:
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

    def export_medspacy_training(
        self,
        export_name: str,
        patient_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Export approved gold to MedSpaCy training format (entities + KB)."""
        with self.neo4j.session() as session:
            if patient_ids:
                candidates = []
                for pid in patient_ids:
                    candidates.extend(list_approved_candidates_for_patient(pid, session))
            else:
                candidates = list_approved_candidates(session=session)

        entities: list[tuple[str, dict[str, Any]]] = []
        kb_rows: list[dict[str, str]] = []

        for candidate in candidates:
            text = candidate.get("deidentified_text", "")
            sent_entities: list[tuple[int, int, str]] = []
            context_flags: list[dict[str, Any]] = []
            for sentence in candidate.get("sentences", []):
                for term in sentence.get("terms", []):
                    concept_id = term.get("coding", {}).get("snomed_concept_id")
                    if not concept_id:
                        continue
                    start = int(term.get("span_start", 0))
                    end = int(term.get("span_end", 0))
                    label = term.get("semantic_tag") or "CLINICAL"
                    sent_entities.append((start, end, label))

                    ctx = term.get("context", {})
                    context_flags.append({
                        "start": start,
                        "end": end,
                        "label": label,
                        "negated": ctx.get("negated", False),
                        "uncertain": ctx.get("uncertain", False),
                        "historical": ctx.get("historical", False),
                        "subject": ctx.get("subject", "patient"),
                        "temporality": ctx.get("temporality", "present"),
                    })

                    kb_rows.append({
                        "evidence": term.get("text", ""),
                        "concept_id": concept_id,
                        "term": term.get("coding", {}).get("snomed_term", ""),
                        "semantic_tag": label,
                        "negated": str(ctx.get("negated", False)),
                    })
            if sent_entities:
                entities.append((
                    text,
                    {"entities": sent_entities, "context_flags": context_flags},
                ))

        export_id = str(uuid.uuid4())
        out_dir = Path("exports")
        out_dir.mkdir(exist_ok=True)
        prefix = f"medspacy_{export_name}_{export_id[:8]}"
        entities_path = out_dir / f"{prefix}_entities.jsonl"
        kb_path = out_dir / f"{prefix}_kb.jsonl"

        with open(entities_path, "w", encoding="utf-8") as f:
            for text, ann in entities:
                f.write(json.dumps([text, ann], ensure_ascii=False) + "\n")

        with open(kb_path, "w", encoding="utf-8") as f:
            for row in kb_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        return {
            "export_id": export_id,
            "entity_count": sum(len(e[1]["entities"]) for e in entities),
            "kb_count": len(kb_rows),
            "encounter_count": len(candidates),
            "export_path": str(entities_path.parent),
        }
