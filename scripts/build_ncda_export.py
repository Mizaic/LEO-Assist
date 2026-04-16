"""Build NCDA-style ground-truth export from raw encounter text.

This is the source-of-truth builder for the Cancer Diagnosis Audit
spreadsheet. It deliberately avoids derived graph artefacts that have
been shown to be unreliable:

    * :EpisodeOfCare nodes (uniform staging_confidence=0.97)
    * :Disease HAS_DISEASE domain tags (e.g. "previous cancer" where
      the source text was actually a benign 2WW rejection)
    * :Procedure nodes (output of the same pipeline)

Instead, every audit-relevant field is re-extracted from the raw
:Encounter text for each episode window, using the regex library in
``scripts.ncda_patterns``. Only primitive stored attributes are read
from the graph: patient DOB/gender, GP practice info, address IMD.

Inputs:
    data/ground_truth/clean_episode_ground_truth.json
    /tmp/all_enc.pkl (fallback: fetched from Neo4j if missing)

Output:
    data/ground_truth/ncda_export.json
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from libs.neo4j_client.client import PatientGraphClient
from scripts.ncda_patterns import (
    ADMIN_HEADER,
    COMORBIDITY_PATTERNS,
    INVESTIGATION_PATTERNS,
    SAFETY_NETTING,
    detect_all_matches,
    detect_symptoms_for_type,
)
from scripts.ncda_staging_adapter import resolve_stage_from_text

REPO_ROOT = Path(__file__).resolve().parent.parent
GT_PATH = REPO_ROOT / "data" / "ground_truth" / "clean_episode_ground_truth.json"
EXPORT_PATH = REPO_ROOT / "data" / "ground_truth" / "ncda_export.json"
PICKLE_PATH = Path("/tmp/all_enc.pkl")

log = logging.getLogger("ncda_export")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_ground_truth() -> list[dict[str, Any]]:
    """Return the list of clean episode ground-truth records."""
    with GT_PATH.open() as f:
        return json.load(f)


def load_encounters() -> list[dict[str, Any]]:
    """Return encounter records. Prefers /tmp/all_enc.pkl; refetches if absent."""
    if PICKLE_PATH.exists():
        with PICKLE_PATH.open("rb") as f:
            return pickle.load(f)
    log.info("Pickle missing; fetching encounters from Neo4j")
    client = PatientGraphClient()
    query = (
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "RETURN p.id AS pid, e.id AS eid, e.date AS date, e.text AS text"
    )
    rows = client.run(query)
    enc = [
        {"pid": r["pid"], "eid": r["eid"], "date": str(r["date"])[:10], "text": r["text"]}
        for r in rows if r.get("text")
    ]
    with PICKLE_PATH.open("wb") as f:
        pickle.dump(enc, f)
    return enc


def fetch_demographics(pids: list[str]) -> dict[str, dict[str, Any]]:
    """Return {pid: {patient, practice, address}} for each patient id."""
    client = PatientGraphClient()
    query = (
        "MATCH (p:Patient) WHERE p.id IN $pids "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(g) "
        "OPTIONAL MATCH (p)-[:HAS_ADDRESS]->(a) "
        "RETURN p.id AS pid, p.gender AS gender, "
        "p.birthDate AS birth_date, "
        "g.name AS practice_name, g.odsCode AS practice_ods, "
        "g.postcode AS practice_postcode, g.address AS practice_address, "
        "a.postcode AS patient_postcode, a.imd_decile AS imd_decile, "
        "a.lsoa_code AS lsoa_code"
    )
    out: dict[str, dict[str, Any]] = {}
    for row in client.run(query, pids=pids):
        out[row["pid"]] = {
            "gender": row.get("gender"),
            "birth_date": str(row.get("birth_date")) if row.get("birth_date") else None,
            "practice_name": row.get("practice_name"),
            "practice_ods": row.get("practice_ods"),
            "practice_postcode": row.get("practice_postcode"),
            "practice_address": row.get("practice_address"),
            "patient_postcode": row.get("patient_postcode"),
            "imd_decile": row.get("imd_decile"),
            "lsoa_code": row.get("lsoa_code"),
        }
    return out


# ---------------------------------------------------------------------------
# Episode enrichment
# ---------------------------------------------------------------------------
def _to_date(value: Any) -> date | None:
    """Parse ISO-8601 date string to a date object (None on failure)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _index_by_patient(encs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group encounter rows by patient id, sorted by date ascending."""
    by_pid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in encs:
        if row.get("date") and row.get("text"):
            by_pid[row["pid"]].append(row)
    for pid in by_pid:
        by_pid[pid].sort(key=lambda r: r["date"])
    return by_pid


def _window(
    patient_encs: list[dict[str, Any]],
    start: date | None,
    end: date | None,
) -> list[dict[str, Any]]:
    """Return encounters whose date lies in [start, end], inclusive on both sides."""
    out = []
    for e in patient_encs:
        d = _to_date(e["date"])
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        out.append(e)
    return out


def _is_clinical(text: str) -> bool:
    """Return True if the encounter's first line is not an admin header."""
    if not text:
        return False
    first = text.strip().splitlines()[0] if text.strip() else ""
    return not bool(ADMIN_HEADER.match(first))


def _gap_days(a: Any, b: Any) -> int | None:
    """Return inclusive day difference between two dates (None if any missing)."""
    da = _to_date(a)
    db = _to_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def extract_pre_referral_fields(
    ep: dict[str, Any],
    patient_encs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return symptoms, investigations, safety netting, consult count, comorbidities."""
    fp = _to_date(ep.get("first_presentation"))
    ref = _to_date(ep.get("referral"))
    window_start = fp or (ref - timedelta(days=90) if ref else None)
    pre_ref = _window(patient_encs, window_start, ref)
    historic = _window(patient_encs, None, ref)
    joined_pre = "\n".join(e["text"] for e in pre_ref)
    joined_hist = "\n".join(e["text"] for e in historic)
    symptoms = detect_symptoms_for_type(joined_pre, ep["cancer_type"])
    investigations = detect_all_matches(joined_pre, INVESTIGATION_PATTERNS)
    comorbidities = detect_all_matches(joined_hist, COMORBIDITY_PATTERNS)
    safety_netting = bool(SAFETY_NETTING.search(joined_pre))
    consults = sum(1 for e in pre_ref if _is_clinical(e["text"]))
    return {
        "presenting_symptoms": symptoms,
        "investigations_ordered": investigations,
        "investigations_ordered_flag": "Yes" if investigations else "No",
        "comorbidities": comorbidities or ["No co-morbidity"],
        "safety_netting_documented": "Yes" if safety_netting else "Not known",
        "consultations_before_referral": consults,
    }


def extract_stage_fields(
    ep: dict[str, Any],
    patient_encs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve stage for a cancer-confirmed episode via authoritative NDRS rules.

    Only runs for cancer-confirmed episodes. Scans the 90-day post-diagnosis
    window and delegates to ``scripts.ncda_staging_adapter`` which applies the
    UICC 8th edition TNM tables and non-TNM staging systems from
    ``configs/staging_rules``.
    """
    if ep.get("diagnosis_outcome") != "cancer":
        return _empty_stage_fields()
    diag = _to_date(ep.get("diagnosis_date"))
    if not diag:
        return _empty_stage_fields()
    window_end = diag + timedelta(days=90)
    post_diag = _window(patient_encs, diag, window_end)
    joined = "\n".join(e["text"] for e in post_diag)
    stage = resolve_stage_from_text(joined, ep.get("cancer_type", ""))
    return {
        "stage_at_diagnosis": stage["cancer_stage_group"] or None,
        "stage_early_late": stage["cancer_stage"],
        "stage_system": stage["staging_system"],
        "stage_tnm_t": stage["tnm_t"],
        "stage_tnm_n": stage["tnm_n"],
        "stage_tnm_m": stage["tnm_m"],
        "stage_evidence": stage["cancer_stage_raw"],
        "stage_confidence": stage["staging_confidence"],
    }


def _empty_stage_fields() -> dict[str, Any]:
    """Return unset stage fields for episodes where staging is not applicable."""
    return {
        "stage_at_diagnosis": None,
        "stage_early_late": "unknown",
        "stage_system": "unknown",
        "stage_tnm_t": "",
        "stage_tnm_n": "",
        "stage_tnm_m": "",
        "stage_evidence": "",
        "stage_confidence": 0.0,
    }


def compute_intervals(ep: dict[str, Any]) -> dict[str, Any]:
    """Return the four NCDA time-interval metrics (None where dates missing)."""
    return {
        "days_presentation_to_referral": _gap_days(
            ep.get("first_presentation"), ep.get("referral")
        ),
        "days_referral_to_first_seen": _gap_days(
            ep.get("referral"), ep.get("first_seen")
        ),
        "days_presentation_to_diagnosis": _gap_days(
            ep.get("first_presentation"), ep.get("diagnosis_date")
        ),
        "days_referral_to_diagnosis": _gap_days(
            ep.get("referral"), ep.get("diagnosis_date")
        ),
    }


def enrich_episode(
    ep: dict[str, Any],
    patient_encs: list[dict[str, Any]],
    demographics: dict[str, Any],
) -> dict[str, Any]:
    """Combine ground-truth episode with extracted fields + demographics."""
    enriched = dict(ep)
    enriched.update(demographics or {})
    enriched.update(extract_pre_referral_fields(ep, patient_encs))
    enriched.update(extract_stage_fields(ep, patient_encs))
    enriched.update(compute_intervals(ep))
    enriched["where_first_presented"] = _classify_presentation(ep.get("referral_type"))
    enriched["referral_type_label"] = _referral_label(ep.get("referral_type"))
    enriched["diagnosis_label"] = _diagnosis_label(ep)
    return enriched


# ---------------------------------------------------------------------------
# Small lookup helpers (NCDA category vocabulary)
# ---------------------------------------------------------------------------
def _classify_presentation(referral_type: str | None) -> str:
    """Map referral_type to NCDA 'Where did the patient first present?' category."""
    mapping = {
        "ae_initiated": "A&E / Emergency Department",
        "gp_initiated": "GP Surgery",
        "specialist_initiated": "Other primary care facility",
        "screening_initiated": "Other - Screening programme",
    }
    return mapping.get(referral_type or "", "GP Surgery")


def _referral_label(referral_type: str | None) -> str:
    """Map referral_type to NCDA 'Type of referral' category."""
    mapping = {
        "ae_initiated": "Emergency referral (including patient self referral)",
        "gp_initiated": "Urgent / TWW for suspected cancer",
        "specialist_initiated": "Routine / Non-urgent",
        "screening_initiated": "Screening detected",
    }
    return mapping.get(referral_type or "", "Urgent / TWW for suspected cancer")


def _diagnosis_label(ep: dict[str, Any]) -> str:
    """Map cancer_type + diagnosis_outcome to an NCDA 'Diagnosis' category."""
    outcome = ep.get("diagnosis_outcome")
    if outcome == "cancer":
        site_map = {
            "breast": "Breast",
            "lower_gi": "Colorectal",
            "upper_gi": "Upper gastro-intestinal (including stomach and oesophagus)",
            "lung": "Lung",
            "prostate": "Prostate",
            "skin": "Skin - other (includes melanoma, BCC, SCC)",
            "head_neck": "Head and Neck",
            "gynaecology": "Gynaecological - other",
            "urology": "Urological - other",
            "haematology": "Haematological",
            "nss": "Unspecified - non-specific symptoms",
        }
        return site_map.get(ep.get("cancer_type", ""), "Other")
    if outcome == "benign":
        return "Non-cancer diagnosis (benign)"
    return "Unknown / pathway incomplete"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def build_export() -> dict[str, Any]:
    """Top-level orchestration: loads inputs, enriches episodes, returns payload."""
    load_dotenv(REPO_ROOT / "secrets" / ".env.secrets")
    load_dotenv(REPO_ROOT / "secrets" / ".env.config")
    episodes = load_ground_truth()
    encs = load_encounters()
    by_pid = _index_by_patient(encs)
    pids = sorted({ep["patient_id"] for ep in episodes})
    log.info("Fetching demographics for %d patients", len(pids))
    demographics = fetch_demographics(pids)
    log.info("Enriching %d episodes", len(episodes))
    enriched = [
        enrich_episode(ep, by_pid.get(ep["patient_id"], []), demographics.get(ep["patient_id"], {}))
        for ep in episodes
    ]
    return {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "clean_episode_ground_truth.json + raw :Encounter text",
        "notes": (
            "All clinical fields (symptoms, investigations, comorbidities, stage, "
            "safety netting) extracted from raw :Encounter text. Derived nodes "
            "(:EpisodeOfCare, :Disease domain tags, :Procedure) are NOT used."
        ),
        "episode_count": len(enriched),
        "patient_count": len({e["patient_id"] for e in enriched}),
        "episodes": enriched,
    }


def main() -> None:
    """Entry point for CLI invocation."""
    payload = build_export()
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXPORT_PATH.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("Wrote %s (%d episodes)", EXPORT_PATH, payload["episode_count"])


if __name__ == "__main__":
    main()
