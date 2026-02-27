"""Encounter pre-classification via 2-model consensus.

Classifies each encounter as admin_only / document_transfer / clinical
BEFORE extraction. Saves LLM cost by skipping extraction for non-clinical
encounters and provides domain hints for clinical ones.

Uses two cheap models (Haiku + GPT-5-mini) for consensus.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from libs.llm_client.factory import create_llm, LLMResponse
from libs.prompts.registry import get_prompt

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ClassificationResult:
    content_type: str  # admin_only | document_transfer | clinical
    domains: list[str] = field(default_factory=list)
    encounter_purpose: list[str] = field(default_factory=list)
    key_clinical_signals: list[str] = field(default_factory=list)
    expected_semantic_tags: list[str] = field(default_factory=list)
    clinical_significance: str = "medium"
    consensus_agreement: bool = True
    model_a_type: str = ""
    model_b_type: str = ""


@dataclass
class PatientEncounterIndex:
    """Summary of classified encounters for a patient."""
    patient_id: str
    run_id: str = ""
    total: int = 0
    admin_count: int = 0
    document_transfer_count: int = 0
    clinical_count: int = 0
    domain_summary: dict[str, int] = field(default_factory=dict)
    classifications: dict[str, ClassificationResult] = field(default_factory=dict)


def _parse_classification(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def classify_encounter(
    encounter_text: str,
    encounter_id: str = "",
) -> ClassificationResult:
    """Classify a single encounter using 2-model consensus.

    Uses Haiku (AWS small) and GPT-5-mini (Azure small) for cheap classification.
    If they disagree on content_type, defaults to 'clinical' (safe fallback).
    """
    system_prompt = get_prompt("encounter_classify", version=1)
    user_msg = f"Classify this GP encounter:\n\n{encounter_text[:3000]}"

    model_a = create_llm(provider="aws", tier="small")
    model_b = create_llm(provider="azure", tier="small")

    result_a = _call_model(model_a, system_prompt, user_msg, "aws_small")
    result_b = _call_model(model_b, system_prompt, user_msg, "azure_small")

    type_a = result_a.get("content_type", "clinical")
    type_b = result_b.get("content_type", "clinical")

    if type_a not in ("admin_only", "document_transfer", "clinical"):
        type_a = "clinical"
    if type_b not in ("admin_only", "document_transfer", "clinical"):
        type_b = "clinical"

    consensus = type_a == type_b
    content_type = type_a if consensus else "clinical"

    primary = result_a if consensus else (result_a if type_a == "clinical" else result_b)

    return ClassificationResult(
        content_type=content_type,
        domains=primary.get("domains", []),
        encounter_purpose=primary.get("encounter_purpose", []),
        key_clinical_signals=primary.get("key_clinical_signals", []),
        expected_semantic_tags=primary.get("expected_semantic_tags", []),
        clinical_significance=primary.get("clinical_significance", "medium"),
        consensus_agreement=consensus,
        model_a_type=type_a,
        model_b_type=type_b,
    )


def _call_model(
    client: Any,
    system: str,
    user_msg: str,
    label: str,
) -> dict[str, Any]:
    try:
        response: LLMResponse = client.converse(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=512,
            temperature=0.0,
        )
        return _parse_classification(response.text)
    except Exception:
        logger.warning("Classification model %s failed", label, exc_info=True)
        return {"content_type": "clinical"}


def build_patient_encounter_index(
    patient_id: str,
    encounters: list[dict[str, Any]],
    run_id: str = "",
) -> PatientEncounterIndex:
    """Classify all encounters for a patient and build an index.

    Args:
        patient_id: The patient identifier.
        encounters: List of dicts with at least ``encounter_id`` and ``text`` keys.

    Returns:
        PatientEncounterIndex with per-encounter classifications and summary stats.
    """
    index = PatientEncounterIndex(patient_id=patient_id, run_id=run_id, total=len(encounters))

    for enc in encounters:
        enc_id = str(enc.get("encounter_id", enc.get("id", "")))
        text = enc.get("text", "")

        if not text or not text.strip():
            index.admin_count += 1
            index.classifications[enc_id] = ClassificationResult(
                content_type="admin_only",
                consensus_agreement=True,
            )
            continue

        result = classify_encounter(text, enc_id)
        index.classifications[enc_id] = result

        if result.content_type == "admin_only":
            index.admin_count += 1
        elif result.content_type == "document_transfer":
            index.document_transfer_count += 1
        else:
            index.clinical_count += 1
            for domain in result.domains:
                index.domain_summary[domain] = index.domain_summary.get(domain, 0) + 1

    logger.info(
        "Patient %s encounter index: %d total, %d admin, %d doc, %d clinical",
        patient_id, index.total, index.admin_count,
        index.document_transfer_count, index.clinical_count,
    )
    return index


def persist_patient_encounter_classification(
    patient_client: Any,
    patient_id: str,
    run_id: str,
    index: PatientEncounterIndex,
) -> dict[str, Any]:
    """Persist encounter-level classification fields and patient-level index node."""
    updated_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for encounter_id, result in index.classifications.items():
        rows.append(
            {
                "encounter_id": str(encounter_id),
                "classification_content_type": result.content_type,
                "classification_domains": [str(v) for v in result.domains],
                "classification_encounter_purpose": [str(v) for v in result.encounter_purpose],
                "classification_expected_semantic_tags": [
                    str(v) for v in result.expected_semantic_tags
                ],
                "classification_clinical_significance": str(result.clinical_significance),
                "classification_consensus_agreement": bool(result.consensus_agreement),
                "classification_model_a_type": str(result.model_a_type),
                "classification_model_b_type": str(result.model_b_type),
                "classification_run_id": str(run_id),
                "classification_updated_at": updated_at,
            }
        )

    with patient_client.session() as session:
        session.run(
            "MATCH (p:Patient) "
            "WHERE toString(p.id) = $pid "
            "UNWIND $rows AS row "
            "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(e.id) = row.encounter_id "
            "SET e.classification_content_type = row.classification_content_type, "
            "    e.classification_domains = row.classification_domains, "
            "    e.classification_encounter_purpose = row.classification_encounter_purpose, "
            "    e.classification_expected_semantic_tags = row.classification_expected_semantic_tags, "
            "    e.classification_clinical_significance = row.classification_clinical_significance, "
            "    e.classification_consensus_agreement = row.classification_consensus_agreement, "
            "    e.classification_model_a_type = row.classification_model_a_type, "
            "    e.classification_model_b_type = row.classification_model_b_type, "
            "    e.classification_run_id = row.classification_run_id, "
            "    e.classification_updated_at = datetime(row.classification_updated_at)",
            pid=patient_id,
            rows=rows,
        )

        session.run(
            "MATCH (p:Patient) "
            "WHERE toString(p.id) = $pid "
            "MERGE (idx:PatientEncounterIndex {patient_id: $pid, run_id: $run_id}) "
            "SET idx.total = $total, "
            "    idx.admin_count = $admin_count, "
            "    idx.document_transfer_count = $document_transfer_count, "
            "    idx.clinical_count = $clinical_count, "
            "    idx.domain_summary_json = $domain_summary_json, "
            "    idx.classified_count = $classified_count, "
            "    idx.updated_at = datetime(), "
            "    idx.created_at = coalesce(idx.created_at, datetime()) "
            "MERGE (p)-[:HAS_ENCOUNTER_INDEX]->(idx)",
            pid=patient_id,
            run_id=run_id,
            total=index.total,
            admin_count=index.admin_count,
            document_transfer_count=index.document_transfer_count,
            clinical_count=index.clinical_count,
            domain_summary_json=json.dumps(index.domain_summary, sort_keys=True),
            classified_count=len(index.classifications),
        )

    return {
        "patient_id": patient_id,
        "run_id": run_id,
        "total": index.total,
        "classified_count": len(index.classifications),
        "clinical_count": index.clinical_count,
        "non_clinical_count": index.admin_count + index.document_transfer_count,
    }
