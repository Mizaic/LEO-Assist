"""Write audit-verified encounters to the Knowledge Graph as training data.

Atlas trace:
  DO: DO-F1953D1C
  DI: DI-65975321
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F1953D1C")

Only de-identified text is stored. Raw patient/encounter IDs never enter the
KG. Mirrors the DI-ID gate in ``persist.write_gold_training``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL
from libs.cypher.training_candidate_queries import (
    UPDATE_TRAINING_CANDIDATE_STATUS,
    UPSERT_TRAINING_CANDIDATE,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.ner.deid_validator import DeIdValidator
from libs.pipeline_graph.subgraphs.persist import (
    _candidate_id,
    _entity_fingerprint,
)
from libs.utils.deidentify import deidentify_text

logger = logging.getLogger(__name__)

AUDIT_VERIFIED_SOURCE = "audit_verified"
SCHEMA_VERSION = "v4"


def _assertion_from_graph_context(context_val: Any) -> str:
    if context_val is None:
        return "present"
    if isinstance(context_val, str):
        raw = context_val.strip()
        if not raw:
            return "present"
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            return "present"
    elif isinstance(context_val, dict):
        d = context_val
    else:
        return "present"
    a = d.get("assertion")
    if isinstance(a, str) and a.strip():
        return a.strip().lower()
    return "present"


def _span_in_deidentified(haystack: str, needle: str) -> tuple[int, int]:
    if not needle.strip():
        return 0, 0
    lo_h = haystack.lower()
    lo_n = needle.lower().strip()
    i = lo_h.find(lo_n)
    if i < 0:
        return 0, 0
    return i, i + len(needle.strip())


def _canonical_entities(
    deid_encounter_text: str, coded_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in coded_rows:
        ev = row.get("evidence") or row.get("term") or ""
        evidence_raw = str(ev).strip()
        if not evidence_raw:
            continue
        ent_text = deidentify_text(evidence_raw, ner=True)
        start, end = _span_in_deidentified(deid_encounter_text, ent_text)
        label = str(row.get("semantic_tag") or row.get("term") or "finding")
        out.append(
            {
                "text": ent_text,
                "label": label,
                "start": start,
                "end": end,
                "assertion": _assertion_from_graph_context(row.get("context")),
            }
        )
    return out


def write_audit_verified_to_kg(
    *,
    raw_encounter_text: str,
    coded_rows: list[dict[str, Any]],
    quality_score: float,
    verified_by: str,
    assessment: str,
) -> dict[str, Any]:
    """Persist one verified audit outcome to KG if DE-ID validation passes.

    Args:
        raw_encounter_text: Full encounter narrative (may contain PHI).
        coded_rows: Patient-graph rows (evidence, semantic_tag, context, ...).
        quality_score: Audit confidence in [0, 1].
        verified_by: e.g. ``audit_agent`` or ``audit_prefilter``.
        assessment: ``no_issues`` or ``clean`` (logging only).

    Returns:
        ``{"written": bool, "errors": [...], "deid_failed": bool}``
    """
    errors: list[str] = []
    raw = raw_encounter_text or ""
    deid_text = deidentify_text(raw, ner=True)

    canonical = _canonical_entities(deid_text, coded_rows)

    validator = DeIdValidator()
    check_payload = {
        "text": deid_text,
        "entities": [
            {"text": e.get("text", ""), "entity_id": i} for i, e in enumerate(canonical)
        ],
    }
    deid_issues = validator.check_record(check_payload)
    candidate_id = _candidate_id(deid_text)
    kg = KnowledgeGraphClient()
    try:
        if deid_issues:
            detail = ", ".join(i.issue_type for i in deid_issues[:5])
            errors.append(f"deid_failed: {detail}")
            logger.warning(
                "audit.kg_writeback blocked (assessment=%s candidate=%s): %s",
                assessment,
                candidate_id[:12],
                errors[-1],
            )
            try:
                with kg.session() as session:
                    session.run(
                        UPSERT_TRAINING_CANDIDATE,
                        candidate_id=candidate_id,
                        text=deid_text,
                        source=AUDIT_VERIFIED_SOURCE,
                        status="failed",
                        schema_version=SCHEMA_VERSION,
                    )
                    session.run(
                        UPDATE_TRAINING_CANDIDATE_STATUS,
                        candidate_id=candidate_id,
                        status="failed",
                    )
            except Exception:
                logger.exception("audit.kg_writeback: mark failed")
            return {
                "written": False,
                "errors": errors,
                "deid_failed": True,
            }

        label_id = _entity_fingerprint(deid_text, canonical)
        with kg.session() as session:
            session.run(
                UPSERT_TRAINING_CANDIDATE,
                candidate_id=candidate_id,
                text=deid_text,
                source=AUDIT_VERIFIED_SOURCE,
                status="processing",
                schema_version=SCHEMA_VERSION,
            )
            session.run(
                UPSERT_GOLD_LABEL,
                label_id=label_id,
                text=deid_text,
                entities_json=json.dumps(canonical),
                source=AUDIT_VERIFIED_SOURCE,
                verified_by=verified_by,
                candidate_id=candidate_id,
                quality_score=float(quality_score),
                schema_version=SCHEMA_VERSION,
            )
            session.run(
                UPDATE_TRAINING_CANDIDATE_STATUS,
                candidate_id=candidate_id,
                status="completed",
            )
        logger.info(
            "audit.kg_writeback ok assessment=%s candidate=%s label=%s",
            assessment,
            candidate_id[:12],
            label_id[:12],
        )
        return {"written": True, "errors": errors, "deid_failed": False}
    except Exception as exc:
        logger.exception("audit.kg_writeback: KG write failed")
        errors.append(f"kg_write: {exc}")
        return {"written": False, "errors": errors, "deid_failed": False}
    finally:
        kg.close()
