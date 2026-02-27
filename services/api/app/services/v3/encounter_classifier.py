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
from dataclasses import dataclass, field
from typing import Any

from libs.llm_client.factory import create_llm, LLMResponse
from libs.prompts.registry import get_prompt

logger = logging.getLogger(__name__)

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
) -> PatientEncounterIndex:
    """Classify all encounters for a patient and build an index.

    Args:
        patient_id: The patient identifier.
        encounters: List of dicts with at least ``encounter_id`` and ``text`` keys.

    Returns:
        PatientEncounterIndex with per-encounter classifications and summary stats.
    """
    index = PatientEncounterIndex(patient_id=patient_id, total=len(encounters))

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
