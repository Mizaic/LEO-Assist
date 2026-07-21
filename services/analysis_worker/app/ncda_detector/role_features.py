"""Stage 4 - Role classifier feature extraction.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Pure functions that transform an encounter row into a feature dict suitable
for downstream sklearn pipelines (DictVectorizer + classifier) or, in
production, LightGBM.

All features are *deterministic* given (text, flags, encounter_date,
vector); no I/O. The trainer and inference modules import this so the same
features are extracted at train and predict time.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from libs.domains.read_code_ncda_lookup import (
    TREATMENT_DRUG_TOKENS,
    lookup_read_code,
)
from services.analysis_worker.app.ncda_detector.audit_rules import (
    extract_read_codes,
)

# Five canonical roles plus 'none'; outcome attribute lives on dx only.
NCDA_ROLES: tuple[str, ...] = ("ftr", "seen", "dx", "treatment", "none")

# Curated phrase patterns one per role; expanded versions of audit_rules.py
# patterns to keep features and audit rules in lockstep.
_PHRASE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ftr": re.compile(
        r"\b(2WW|2 ?week ?wait|fast.?track|FTS|USC|urgent suspected cancer"
        r"|PRISM 2WW|fast.?track referral|two.?week.?wait)\b",
        re.IGNORECASE,
    ),
    "seen": re.compile(
        r"\b(seen in|specialist clinic|outpatient (?:clinic|appt)"
        r"|attended.*(?:clinic|consultant|appointment)"
        r"|review in clinic|clinic letter|seen by)\b",
        re.IGNORECASE,
    ),
    "dx_found": re.compile(
        r"\b(malignant|carcinoma|adenocarcinoma|lymphoma|melanoma"
        r"|sarcoma|tumour confirmed|new (cancer )?diagnosis|new episode"
        r"|histology.*malignant)\b",
        re.IGNORECASE,
    ),
    "dx_excluded": re.compile(
        r"\b(no malignancy|benign|cancer ruled out|cancer excluded"
        r"|d/?c (from|after).*(2WW|pathway|clinic)"
        r"|discharged from (clinic|cancer|2WW|pathway)"
        r"|all clear|no evidence of (cancer|malignancy))\b",
        re.IGNORECASE,
    ),
    "treatment": re.compile(
        r"\b(chemotherapy|radiotherapy|brachytherapy|mastectomy|prostatectomy"
        r"|lumpectomy|cystectomy|colectomy|hysterectomy|oesophagectomy|nephrectomy"
        r"|orchidectomy|thyroidectomy|chemo administration|first cycle|cycle 1"
        r"|started chemo|hormone therapy|targeted therapy|immunotherapy)\b",
        re.IGNORECASE,
    ),
}


def phrase_features(text: str) -> dict[str, int]:
    """Return one boolean feature per curated phrase pattern."""
    out: dict[str, int] = {}
    for name, pattern in _PHRASE_PATTERNS.items():
        out[f"phrase_{name}"] = 1 if pattern.search(text or "") else 0
    return out


def read_code_features(text: str) -> dict[str, int]:
    """Boolean per-role flags derived from curated Read-code lookup."""
    out = {f"code_{role}": 0 for role in NCDA_ROLES}
    out["code_dx_found"] = 0
    out["code_dx_excluded"] = 0
    for token in extract_read_codes(text or ""):
        looked = lookup_read_code(token)
        if looked is None:
            continue
        role, outcome = looked
        out[f"code_{role}"] = 1
        if role == "dx" and outcome == "cancer_found":
            out["code_dx_found"] = 1
        elif role == "dx" and outcome == "cancer_excluded":
            out["code_dx_excluded"] = 1
    if _bare_drug_token(text or ""):
        out["code_treatment"] = 1
    return out


def _bare_drug_token(text: str) -> bool:
    upper = text.upper()
    return any(drug in upper for drug in TREATMENT_DRUG_TOKENS)


def flag_features(flags: str | None) -> dict[str, int]:
    """Parse Encounter.flags string into NCDA-relevant booleans."""
    f = (flags or "").lower()
    return {
        "flag_face_to_face": int("face to face" in f),
        "flag_telephone": int("telephone" in f),
        "flag_admin_event": int("administration event" in f or "admin event" in f),
        "flag_back_dated": int("back-dated" in f or "back dated" in f),
        "flag_linked_to_appt": int("linked to appointment" in f),
        "flag_amended": int("amended" in f),
    }


def date_features(encounter_date: str | None) -> dict[str, int]:
    """day-of-week, day-of-month, month-of-year (defaults zero on missing)."""
    parsed = _parse_date(encounter_date)
    if parsed is None:
        return {"date_dow": 0, "date_dom": 0, "date_moy": 0}
    return {
        "date_dow": parsed.isoweekday(),
        "date_dom": parsed.day,
        "date_moy": parsed.month,
    }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y/%m/%d").date()
        except ValueError:
            return None


def vector_features(vector: Sequence[float] | None) -> dict[str, float]:
    """Return v_i feature per dimension. Empty when vector is None."""
    if vector is None:
        return {}
    return {f"v{i}": float(v) for i, v in enumerate(vector)}


def vector_delta_features(
    vector: Sequence[float] | None,
    archetypes: dict[str, Sequence[float]] | None,
) -> dict[str, float]:
    """Cosine to per-role archetype mean (one delta per role)."""
    if vector is None or not archetypes:
        return {}
    out: dict[str, float] = {}
    v = list(vector)
    v_norm = _norm(v)
    if v_norm == 0:
        return {f"vdelta_{role}": 0.0 for role in archetypes}
    for role, archetype in archetypes.items():
        a = list(archetype)
        a_norm = _norm(a)
        if a_norm == 0:
            out[f"vdelta_{role}"] = 0.0
            continue
        dot = sum(x * y for x, y in zip(v, a))
        out[f"vdelta_{role}"] = float(dot / (v_norm * a_norm))
    return out


def _norm(v: Sequence[float]) -> float:
    return float(sum(x * x for x in v) ** 0.5)


def extract_features(
    *,
    text: str,
    flags: str | None,
    encounter_date: str | None,
    vector: Sequence[float] | None = None,
    archetypes: dict[str, Sequence[float]] | None = None,
) -> dict[str, Any]:
    """Combined feature dict ready for DictVectorizer."""
    features: dict[str, Any] = {}
    features.update(phrase_features(text))
    features.update(read_code_features(text))
    features.update(flag_features(flags))
    features.update(date_features(encounter_date))
    features.update(vector_features(vector))
    features.update(vector_delta_features(vector, archetypes))
    return features


def compute_role_archetypes(
    rows: Iterable[dict],
) -> dict[str, list[float]]:
    """Mean vector per role across labelled rows. Skip rows with no vector."""
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for r in rows:
        v = r.get("vector")
        role = r.get("role")
        if v is None or role is None:
            continue
        if role not in sums:
            sums[role] = [0.0] * len(v)
            counts[role] = 0
        for i, x in enumerate(v):
            sums[role][i] += float(x)
        counts[role] += 1
    archetypes: dict[str, list[float]] = {}
    for role, total in sums.items():
        if counts[role] == 0:
            continue
        archetypes[role] = [t / counts[role] for t in total]
    return archetypes
