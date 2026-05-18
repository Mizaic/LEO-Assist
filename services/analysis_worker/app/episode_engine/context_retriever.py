"""Context milestone retrieval: two-track pre-filter for the milestone extractor.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-2C015ADE

Track 1 -- VECTOR: Bio_ClinicalBERT cosine similarity for context types
  whose encounter text is structurally distinctive:
    referral_sent, referral_admin, related_specialist_visit,
    specialist_diagnostics, related_correspondence

Track 2 -- ROLE: regex match on the encounter header line for context
  types that are not text-distinctive but are role-distinctive:
    related_gp_visit       -> header contains Clinical Practitioner / Dr / Nurse
    primary_care_investigations -> header/text contains auto-filed results or bloods

The output is a compact formatted block injected into the LLM USER prompt
so the model can focus on a small candidate set per context type rather
than scanning hundreds of encounters.

Feature flag: set EPISODE_ENGINE_CONTEXT_HINTS=0 to disable entirely.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed texts -- written in EMIS GP record style so Bio_ClinicalBERT
# similarity is meaningful within the stored encounter vector space.
# ---------------------------------------------------------------------------
_VECTOR_SEEDS: dict[str, str] = {
    "referral_sent": (
        "Fast track referral suspected cancer Choice and booking enhanced "
        "services administration XaMJa 2WW Hospital referral Medical Secretary"
    ),
    "referral_admin": (
        "Choice and booking enhanced services administration patient "
        "awaiting OPD appointment 2WW admin booking Medical Secretary"
    ),
    "related_specialist_visit": (
        "outpatient clinic appointment consultant hospital follow-up "
        "specialist attendance review secondary care"
    ),
    "specialist_diagnostics": (
        "biopsy CT scan MRI mammogram ultrasound colonoscopy endoscopy "
        "fine needle aspiration histology New Episode"
    ),
    "related_correspondence": (
        "Medical Secretary clinic letter hospital to surgery correspondence "
        "discharge summary outcome secondary care letter"
    ),
}

# Top-N per vector type returned to the LLM
_TOP_K_VECTOR = 5

# ---------------------------------------------------------------------------
# Role patterns for metadata track
# ---------------------------------------------------------------------------
_ROLE_PATTERNS: dict[str, re.Pattern] = {
    "related_gp_visit": re.compile(
        r"\(Clinical Practitioner Access Role\)|"
        r"\(Health Professional Access Role\)|"
        r"\(Dr\)\s|"
        r"\(Nurse Access Role\)",
        re.IGNORECASE,
    ),
    "primary_care_investigations": re.compile(
        r"Auto-filed|"
        r"\bblood test\b|"
        r"\bSerum\b|"
        r"urine.*creat|"
        r"\bPSA\b|"
        r"\bFBC\b|"
        r"\bHbA1c\b|"
        r"haemoglobin|"
        r"cholesterol|"
        r"\beGFR\b|"
        r"investigations requested|"
        r"bloods ordered|"
        r"result received",
        re.IGNORECASE,
    ),
}

_TOP_K_ROLE = 5

# Serialise encode() calls: SentenceTransformer on MPS can misbehave
# when two threads call encode() simultaneously.
_ENCODE_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------
_LOAD_VECTORS_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.vector IS NOT NULL
  AND e.date >= $start_date
  AND e.date <= $end_date
RETURN e.id     AS encounter_id,
       e.date   AS date,
       e.vector AS vector
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_vectors(
    client: "PatientGraphClient",
    patient_id: str,
    start: str,
    end: str,
) -> list[dict]:
    try:
        return (
            client.run(
                _LOAD_VECTORS_Q,
                patient_id=patient_id,
                start_date=start,
                end_date=end,
            )
            or []
        )
    except Exception:
        logger.warning(
            "context_retriever: vector load failed for patient %s",
            patient_id,
            exc_info=True,
        )
        return []


_embedder_lock = threading.Lock()
_embedder_singleton = None
_embedder_failed = False


def _get_embedder():
    """Return a process-wide Bio_ClinicalBERT SentenceTransformer, or None.

    Uses its own lazy singleton so the import does not depend on the
    few_shot_selector module-level guard (which can be False in pytest
    sessions where sentence_transformers loads after few_shot_selector).
    """
    global _embedder_singleton, _embedder_failed  # noqa: PLW0603
    if _embedder_failed:
        return None
    if _embedder_singleton is not None:
        return _embedder_singleton
    with _embedder_lock:
        if _embedder_singleton is not None:
            return _embedder_singleton
        try:
            from sentence_transformers import SentenceTransformer

            model_name = os.getenv("VECTOR_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
            logger.info("context_retriever: loading embedder %s", model_name)
            _embedder_singleton = SentenceTransformer(model_name, device=None)
            return _embedder_singleton
        except Exception:
            logger.warning(
                "context_retriever: embedder load failed -- "
                "vector hints disabled for this process",
                exc_info=True,
            )
            _embedder_failed = True
            return None


def _cosine_top_k(
    seed_text: str,
    enc_rows: list[dict],
    top_k: int,
) -> list[str]:
    """Embed seed_text and return top-k encounter_ids by cosine similarity."""
    if not enc_rows:
        return []
    embedder = _get_embedder()
    if embedder is None:
        return []
    try:
        with _ENCODE_LOCK:
            qvec = embedder.encode([seed_text], normalize_embeddings=True)[0]
        matrix = np.array([r["vector"] for r in enc_rows], dtype=np.float32)
        scores = matrix @ qvec.astype(np.float32)
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [enc_rows[int(i)]["encounter_id"] for i in top_idx]
    except Exception:
        logger.warning("context_retriever: cosine ranking failed", exc_info=True)
        return []


def _role_filter_top_k(
    milestone_type: str,
    encounter_index: dict[str, dict[str, Any]],
    window_ids: set[str],
    top_k: int,
) -> list[str]:
    """Return up to top_k encounter_ids matching the role/text pattern."""
    pat = _ROLE_PATTERNS.get(milestone_type)
    if pat is None:
        return []
    matches: list[tuple[str, str]] = []
    for eid in window_ids:
        rec = encounter_index.get(eid) or {}
        text = rec.get("full_snippet") or rec.get("text") or ""
        # Check the first two lines (header + first content line)
        head = "\n".join(text.splitlines()[:2])[:300]
        if pat.search(head):
            matches.append((eid, str(rec.get("date") or "")))
    matches.sort(key=lambda x: x[1])
    return [m[0] for m in matches[:top_k]]


def _format_candidates(
    eids: list[str],
    encounter_index: dict[str, dict[str, Any]],
) -> str:
    parts: list[str] = []
    for eid in eids:
        rec = encounter_index.get(eid) or {}
        date = rec.get("date") or "?"
        parts.append(f"{eid[:8]}({date})")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_context_hints(
    *,
    patient_id: str,
    window_start: str,
    window_end: str,
    encounter_index: dict[str, dict[str, Any]],
    client: "PatientGraphClient",
) -> str:
    """Return a CONTEXT MILESTONE HINTS block for injection into the LLM prompt.

    Returns an empty string if the feature is disabled, no vectors are
    available, or any failure occurs -- the caller always gets a safe fallback.
    """
    if os.getenv("EPISODE_ENGINE_CONTEXT_HINTS", "1") in ("0", "false", "False"):
        return ""

    try:
        return _build_hints(
            patient_id=patient_id,
            window_start=window_start,
            window_end=window_end,
            encounter_index=encounter_index,
            client=client,
        )
    except Exception:
        logger.warning(
            "context_retriever: hints build failed for patient %s",
            patient_id,
            exc_info=True,
        )
        return ""


def _build_hints(
    *,
    patient_id: str,
    window_start: str,
    window_end: str,
    encounter_index: dict[str, dict[str, Any]],
    client: "PatientGraphClient",
) -> str:
    window_ids: set[str] = {
        eid
        for eid, rec in encounter_index.items()
        if rec.get("date") and str(window_start) <= str(rec["date"]) <= str(window_end)
    }
    if not window_ids:
        return ""

    # Load stored vectors for the window (single round-trip)
    enc_rows = _load_vectors(client, patient_id, window_start, window_end)
    enc_rows = [r for r in enc_rows if r.get("encounter_id") in window_ids]

    lines: list[str] = []

    # Track 1 -- vector similarity
    for mt, seed in _VECTOR_SEEDS.items():
        cands = _cosine_top_k(seed, enc_rows, _TOP_K_VECTOR)
        if cands:
            lines.append(f"  {mt}: {_format_candidates(cands, encounter_index)}")

    # Track 2 -- role/metadata filter
    for mt in ("related_gp_visit", "primary_care_investigations"):
        cands = _role_filter_top_k(mt, encounter_index, window_ids, _TOP_K_ROLE)
        if cands:
            lines.append(f"  {mt}: {_format_candidates(cands, encounter_index)}")

    if not lines:
        return ""

    return (
        "CONTEXT MILESTONE HINTS (semantic and role pre-scan -- short-list of\n"
        "encounter IDs most likely to carry each context milestone. Check each\n"
        "against the encounter text above. Only emit if evidence truly matches\n"
        "the milestone definition. IDs are first 8 chars; dates in brackets):\n"
        + "\n".join(lines)
    )
