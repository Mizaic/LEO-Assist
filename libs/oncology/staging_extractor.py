"""NCDA cancer episode staging extractor.

Scans milestoned encounter texts for staging information and returns a
:class:`StagingResult` carrying the detected system, raw value, and an
early/intermediate/late classification.

Supported staging systems (in priority order):
    1. TNM  – full TxNxMx notation
    2. Gleason – Gleason X+Y (prostate)
    3. Breslow – Breslow X.Xmm (melanoma)
    4. Clark – Clark level I-V (melanoma)
    5. Binet – Binet A/B/C (CLL)
    6. FIGO – FIGO stage I-IV (gynaecological)
    7. Dukes – Dukes A-D (colorectal)
    8. Ann Arbor – stages I-IV (lymphoma)
    9. ISUP – ISUP grade 1-5 (prostate)
   10. pT_stage – standalone pT/T notation
   11. Nottingham – grade 1-3 ductal/lobular or explicit NHG/Nottingham grade
   12. receptor_status – ER/HER2 (breast, prognostic, not stage)
   13. generic_stage – stage I-IV plain text (noisy, lowest priority)

Early / intermediate / late mappings:
    TNM T1-2 N0 M0  → early        T3-4 or N+ or M1 → late
    Gleason ≤6      → early        7 → intermediate  ≥8 → late
    Breslow <0.8mm  → early        0.8-2mm → intermediate  >2mm → late
    Clark I-III     → early        IV-V → late
    Binet A         → early        B → intermediate   C → late
    FIGO I-II       → early        III-IV → late
    Dukes A-B       → early        C-D → late
    Ann Arbor I-II  → early        III-IV → late
    ISUP 1-2        → early        3-5 → late
    pT_stage T1-2   → early        T3-4 → late
    Nottingham 1    → early        2 → intermediate  3 → late
    receptor_status → unknown (prognostic marker, not stage)
    generic_stage I-II → early     III-IV → late   (confidence 0.65)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class StagingResult:
    """Extracted staging information for one cancer episode."""

    system: str
    """Primary staging system detected (e.g. ``'TNM'``, ``'Gleason'``)."""

    raw_value: str
    """Verbatim extracted value (e.g. ``'T3aN0'``, ``'3+4=7'``, ``'3.7mm'``)."""

    early_late: str
    """Staging interpretation: ``'early'``, ``'intermediate'``, ``'late'``,
    ``'unknown'`` (found but not classifiable), or ``'not_found'``."""

    confidence: float
    """Confidence in the extraction + classification, 0.0 – 1.0."""

    systems_found: list[str] = field(default_factory=list)
    """All staging systems detected in the combined text (for multi-system episodes)."""


NO_STAGING = StagingResult(
    system="none",
    raw_value="",
    early_late="not_found",
    confidence=0.0,
    systems_found=[],
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


def _roman(s: str) -> int:
    s = s.strip().upper()
    if s in _ROMAN:
        return _ROMAN[s]
    # handle 2-char prefix (e.g. "IIA" → "II")
    for k, v in sorted(_ROMAN.items(), key=lambda x: -len(x[0])):
        if s.startswith(k):
            return v
    try:
        return int(s)
    except ValueError:
        return 0


def _classify_tnm(m: re.Match) -> tuple[str, float]:
    t = int(m.group(1))
    n = int(m.group(2))
    mv = int(m.group(3))
    if mv >= 1 or n >= 2:
        return "late", 0.95
    if t >= 3:
        return "late", 0.92
    if n == 1:
        return "intermediate", 0.88
    return "early", 0.92


def _classify_gleason(m: re.Match) -> tuple[str, float]:
    total = int(m.group(1)) + int(m.group(2))
    if total <= 6:
        return "early", 0.95
    if total == 7:
        return "intermediate", 0.90
    return "late", 0.95


def _classify_breslow(m: re.Match) -> tuple[str, float]:
    mm = float(m.group(1))
    if mm < 0.8:
        return "early", 0.90
    if mm < 2.0:
        return "intermediate", 0.88
    return "late", 0.90


def _classify_clark(m: re.Match) -> tuple[str, float]:
    level = _roman(m.group(1))
    return ("early", 0.80) if level <= 3 else ("late", 0.82)


def _classify_binet(m: re.Match) -> tuple[str, float]:
    s = m.group(1).upper()
    if s == "A":
        return "early", 0.90
    if s == "C":
        return "late", 0.90
    return "intermediate", 0.88


def _classify_figo(m: re.Match) -> tuple[str, float]:
    n = _roman(m.group(1))
    return ("early", 0.85) if n <= 2 else ("late", 0.85)


def _classify_dukes(m: re.Match) -> tuple[str, float]:
    s = m.group(1).upper()
    return ("early", 0.85) if s in ("A", "B") else ("late", 0.85)


def _classify_ann_arbor(m: re.Match) -> tuple[str, float]:
    n = _roman(m.group(1))
    return ("early", 0.85) if n <= 2 else ("late", 0.85)


def _classify_isup(m: re.Match) -> tuple[str, float]:
    g = int(m.group(1))
    if g <= 2:
        return "early", 0.85
    if g == 3:
        return "intermediate", 0.85
    return "late", 0.88


def _classify_pt(m: re.Match) -> tuple[str, float]:
    """pT_stage: pT1-2 → early, pT3-4 → late.  N/M suffix respected if present."""
    s = m.group(1).upper()
    t_m = re.match(r"T([0-4])", s)
    if not t_m:
        return "unknown", 0.50
    t = int(t_m.group(1))
    n_m = re.search(r"N([0-3])", s)
    mv_m = re.search(r"M([01])", s)
    n = int(n_m.group(1)) if n_m else -1
    mv = int(mv_m.group(1)) if mv_m else -1
    if mv == 1 or n >= 2:
        return "late", 0.90
    if t >= 3:
        return "late", 0.88
    if n == 1:
        return "intermediate", 0.85
    return "early", 0.88


def _classify_nottingham(m: re.Match) -> tuple[str, float]:
    # group(1) may be digit or Roman numeral
    raw = m.group(1)
    g = int(raw) if raw.isdigit() else _roman(raw)
    if g == 1:
        return "early", 0.85
    if g == 2:
        return "intermediate", 0.85
    return "late", 0.88


def _classify_generic(m: re.Match) -> tuple[str, float]:
    s = m.group(1)
    n = _roman(s) if not s.isdigit() else int(s)
    if n in (1, 2):
        return "early", 0.70
    if n in (3, 4):
        return "late", 0.70
    return "unknown", 0.40


# ---------------------------------------------------------------------------
# Pattern registry  (applied in priority order; first match wins per system)
# ---------------------------------------------------------------------------

_PATTERNS: list[dict] = [
    # --- Full TNM (T+N+M all present — highest confidence) ---
    {
        "system": "TNM",
        "re": re.compile(r"\bT([0-4])[a-c]?\s*N([0-3])\s*M([01])\b"),
        "extract": lambda m: m.group(0).replace(" ", ""),
        "classify": _classify_tnm,
        "priority": 0,
    },
    # --- Partial TNM (T+N without M — common in GP records) ---
    {
        "system": "TNM",
        "re": re.compile(r"\bT([0-4])[a-c]?\s*N([0-3])\b(?!\s*M)"),
        "extract": lambda m: m.group(0).replace(" ", ""),
        # Treat as M0 assumption: T3N0 → late (T≥3), T1-2N0 → early
        "classify": lambda m: (
            ("late", 0.88) if (int(m.group(1)) >= 3 or int(m.group(2)) >= 1)
            else ("early", 0.85)
        ),
        "priority": 1,
    },
    # --- Gleason ---
    {
        "system": "Gleason",
        "re": re.compile(r"Gleason\s+(\d)\s*[+]\s*(\d)(?:\s*=\s*\d+)?", re.I),
        "extract": lambda m: m.group(0),
        "classify": _classify_gleason,
        "priority": 1,
    },
    # --- Breslow (explicit keyword required to avoid spurious mm matches) ---
    {
        "system": "Breslow",
        "re": re.compile(r"Breslow[^;.\n]{0,30}?(\d+\.?\d*)\s*mm", re.I),
        "extract": lambda m: f"{m.group(1)}mm (Breslow)",
        "classify": _classify_breslow,
        "priority": 2,
    },
    # --- Breslow without keyword: melanoma context, plain decimal + mm ---
    # Only applied when cancer_type is Melanoma (guarded at call site)
    {
        "system": "Breslow",
        "re": re.compile(r"\b(\d+\.\d+)\s*mm\b"),
        "extract": lambda m: f"{m.group(1)}mm",
        "classify": _classify_breslow,
        "priority": 3,
        "melanoma_only": True,
    },
    # --- Clark level ---
    {
        "system": "Clark",
        "re": re.compile(r"Clark\s*(?:level)?\s*:?\s*([IViv]+|\d)", re.I),
        "extract": lambda m: f"Clark level {m.group(1).upper()}",
        "classify": _classify_clark,
        "priority": 4,
    },
    # --- Binet (CLL) ---
    {
        "system": "Binet",
        "re": re.compile(r"Binet\s+(?:stage\s+)?([A-Ca-c])\b", re.I),
        "extract": lambda m: f"Binet {m.group(1).upper()}",
        "classify": _classify_binet,
        "priority": 5,
    },
    # --- FIGO (gynaecological) ---
    {
        "system": "FIGO",
        "re": re.compile(r"FIGO\s+(?:stage\s+)?([IViv]{1,4}[A-Ca-c]?)\b", re.I),
        "extract": lambda m: f"FIGO {m.group(1).upper()}",
        "classify": _classify_figo,
        "priority": 6,
    },
    # --- Dukes (colorectal) ---
    {
        "system": "Dukes",
        "re": re.compile(r"Dukes['']?\s+([A-Da-d])\b", re.I),
        "extract": lambda m: f"Dukes {m.group(1).upper()}",
        "classify": _classify_dukes,
        "priority": 7,
    },
    # --- Ann Arbor (lymphoma) ---
    {
        "system": "Ann_Arbor",
        "re": re.compile(r"Ann\s+Arbor\s+(?:stage\s+)?([IViv]{1,3}[A-Ba-b]?)\b", re.I),
        "extract": lambda m: f"Ann Arbor {m.group(1).upper()}",
        "classify": _classify_ann_arbor,
        "priority": 8,
    },
    # --- ISUP grade (prostate) ---
    {
        "system": "ISUP",
        "re": re.compile(r"ISUP\s+grade\s+(\d)\b", re.I),
        "extract": lambda m: f"ISUP grade {m.group(1)}",
        "classify": _classify_isup,
        "priority": 9,
    },
    # --- pT stage standalone (with optional N/M suffix) ---
    {
        "system": "pT_stage",
        "re": re.compile(r"\bp(T[0-4][a-c]?(?:N[0-3])?(?:M[01])?)\b"),
        "extract": lambda m: f"p{m.group(1).upper()}",
        "classify": _classify_pt,
        "priority": 10,
    },
    # --- Nottingham explicit ("Nottingham grade X" / "NHG X") ---
    {
        "system": "Nottingham",
        "re": re.compile(r"(?:Nottingham\s+grade|NHG)\s+([1-3IViv])", re.I),
        "extract": lambda m: f"Nottingham grade {m.group(1)}",
        "classify": _classify_nottingham,
        "priority": 11,
    },
    # --- Nottingham inline ("grade 2 ductal" / "grade 3 lobular") ---
    {
        "system": "Nottingham",
        "re": re.compile(r"\bgrade\s+([1-3])\s+(?:ductal|lobular|breast|invasive)", re.I),
        "extract": lambda m: f"grade {m.group(1)} ductal/lobular",
        "classify": _classify_nottingham,
        "priority": 12,
    },
    # --- ER / HER2 receptor status (Breast only; not a true staging system) ---
    # Only enabled when cancer_type is Breast (guarded at call site).
    {
        "system": "receptor_status",
        "re": re.compile(
            r"(?:\bER[+-](?:ve)?\b|\bER\s+(?:positive|negative)\b"
            r"|\bHER2[+-](?:ve)?\b|\bHER2\s+(?:positive|negative|pos|neg)\b)",
            re.I,
        ),
        "extract": lambda m: m.group(0),
        "classify": lambda m: ("unknown", 0.50),
        "priority": 13,
        "breast_only": True,
    },
    # --- Generic stage I-IV (lowest priority, noisy) ---
    {
        "system": "generic_stage",
        "re": re.compile(r"\bstage\s+([IViv]{1,3}|\d)\b(?!\s*\d)", re.I),
        "extract": lambda m: f"stage {m.group(1)}",
        "classify": _classify_generic,
        "priority": 14,
    },
]

# Systems that convey a true early/late classification
_CLASSIFIABLE_SYSTEMS = frozenset(
    {
        "TNM",
        "Gleason",
        "Breslow",
        "Clark",
        "Binet",
        "FIGO",
        "Dukes",
        "Ann_Arbor",
        "ISUP",
        "pT_stage",
        "Nottingham",
        "generic_stage",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_staging(cancer_type: str, *texts: str) -> StagingResult:
    """Detect staging information from one or more encounter text fragments.

    Parameters
    ----------
    cancer_type:
        Canonical NCDA cancer type (e.g. ``'Prostate'``, ``'Melanoma'``).
        Used to enable context-sensitive patterns (e.g. plain-mm Breslow for
        Melanoma).
    *texts:
        One or more encounter text strings (dx, ftr, seen, treatment).
        They are concatenated with a space separator before searching.

    Returns
    -------
    StagingResult
        The highest-priority staging result found, or :data:`NO_STAGING` if
        nothing was detected.
    """
    combined = " ".join(t for t in texts if t)
    if not combined.strip():
        return NO_STAGING

    ct_lower = cancer_type.lower()
    is_melanoma = ct_lower == "melanoma"
    is_breast = ct_lower in ("breast",)

    # Collect all matches (system → best match per system)
    per_system: dict[str, tuple[int, StagingResult]] = {}

    for spec in _PATTERNS:
        # Context-restricted patterns
        if spec.get("melanoma_only") and not is_melanoma:
            continue
        if spec.get("breast_only") and not is_breast:
            continue
        m = spec["re"].search(combined)
        if not m:
            continue
        early_late, conf = spec["classify"](m)
        raw_value = spec["extract"](m)
        result = StagingResult(
            system=spec["system"],
            raw_value=raw_value,
            early_late=early_late,
            confidence=conf,
            systems_found=[],
        )
        priority = spec["priority"]
        # Keep the highest-priority (lowest number) hit per system
        existing = per_system.get(spec["system"])
        if existing is None or priority < existing[0]:
            per_system[spec["system"]] = (priority, result)

    if not per_system:
        return NO_STAGING

    # Pick the overall best result: prefer classifiable systems in priority order
    classifiable = {
        sys: (pri, res)
        for sys, (pri, res) in per_system.items()
        if sys in _CLASSIFIABLE_SYSTEMS
    }
    pool = classifiable if classifiable else per_system
    best_priority, best = min(pool.values(), key=lambda x: x[0])

    all_systems = sorted(per_system.keys(), key=lambda s: per_system[s][0])
    best.systems_found = all_systems
    return best
