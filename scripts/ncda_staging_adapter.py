"""Apply authoritative NDRS staging rules to free-text episode snippets.

Delegates to :mod:`libs.staging.engine` (UICC 8th site rules + non-TNM
systems in ``configs/staging_rules``). This script is responsible only for:

1. Mapping our coarse ``cancer_type`` labels to candidate site SNOMED codes
   so the engine can pick the right rule file.
2. Harvesting plausible TNM-triplet and explicit-stage substrings from the
   raw encounter text (so the engine gets clean inputs rather than noisy
   free-text).
3. Calling the engine in priority order (TNM > explicit stage > non-TNM
   system) and returning the first concrete result.

The engine's own ``_EXPLICIT_STAGE_RE`` is intentionally broad, which is
fine when the caller has already narrowed the text to a stage phrase
(e.g. "Stage IIIA", "metastatic", "T3N1M0"). We do that narrowing here.
"""

from __future__ import annotations

import re
from typing import Any

from libs.staging.engine import StagingRulesEngine
from libs.staging.tnm_parser import parse_tnm_triplet

# Map our pipeline cancer_type buckets to the SNOMED codes that appear in
# configs/staging_rules/_site_index.json. Each bucket lists candidate codes
# in priority order -- we try them one at a time until a rule matches.
CANCER_TYPE_TO_SNOMED: dict[str, list[str]] = {
    "breast": ["254837009"],
    "lower_gi": ["363508008", "363403002"],
    "upper_gi": ["255080008", "269457002", "363403002"],
    "lung": ["363358000", "363432004", "363494000"],
    "prostate": ["399068003", "236740006"],
    "skin": ["372130007", "126598008"],
    "head_neck": [
        "255056009", "363461003", "363367000", "371982006", "128462008",
    ],
    "gynaecology": [
        "371972005", "363354003", "363443007", "363444001", "363367000",
        "609519004",
    ],
    "urology": [
        "93689003", "93849006", "363458004", "363459007", "363516004",
        "363449006",
    ],
    "haematology": ["310504009", "128462008", "363495004"],
    "nss": [],
}

_ENGINE: StagingRulesEngine | None = None


def _engine() -> StagingRulesEngine:
    """Return a singleton engine with rules pre-loaded."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = StagingRulesEngine()
        _ENGINE.load_rules()
    return _ENGINE


# ---------------------------------------------------------------------------
# Text harvesting -- narrow free text to stage-shaped fragments
# ---------------------------------------------------------------------------
_TNM_RE = re.compile(
    r"\b[cpyr]?T[0-4][a-c]?\s*[cpyr]?N[0-3][a-c]?\s*[cpyr]?M[01][a-c]?\b",
    re.IGNORECASE,
)
_STAGE_GROUP_RE = re.compile(
    r"\bstage\s+(IV[ABC]?|III[ABC]?|II[ABC]?|I[ABC]?|0|[1-4][ABCabc]?)\b",
    re.IGNORECASE,
)
_IN_SITU_RE = re.compile(r"\b(DCIS|LCIS|Tis|in\s+situ)\b", re.IGNORECASE)
_METASTATIC_RE = re.compile(
    r"\b(metastatic|distant\s+metastas\w+|metastases\s+to)\b", re.IGNORECASE,
)


def _harvest_tnm(text: str) -> list[str]:
    """Return every TNM-shaped fragment in the text (deduplicated, order-preserving)."""
    seen: list[str] = []
    for m in _TNM_RE.finditer(text or ""):
        token = m.group(0).upper().replace(" ", "")
        if token not in seen:
            seen.append(token)
    return seen


def _harvest_explicit(text: str) -> list[str]:
    """Return explicit Stage-group fragments like 'Stage IIIA' or 'stage 4'."""
    seen: list[str] = []
    for m in _STAGE_GROUP_RE.finditer(text or ""):
        token = m.group(0)
        if token not in seen:
            seen.append(token)
    return seen


def _harvest_non_tnm(text: str) -> list[str]:
    """Return substrings matching any known non-TNM staging-system alias."""
    if not text:
        return []
    engine = _engine()
    out: list[str] = []
    for system in engine.non_tnm_systems:
        aliases = [a for a in system.get("aliases", []) if a]
        for alias in aliases:
            pattern = re.compile(
                r"\b" + re.escape(alias) + r"\s*(?:stage\s*)?"
                r"([0IVXMAB][0-9IVXMAB/+-]*)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(text):
                fragment = m.group(0)
                if fragment not in out:
                    out.append(fragment)
    return out


# ---------------------------------------------------------------------------
# Stage resolution
# ---------------------------------------------------------------------------
def _try_tnm(text: str, snomed_codes: list[str]) -> dict[str, Any] | None:
    """Try every harvested TNM triplet against each candidate site."""
    for frag in _harvest_tnm(text):
        tnm = parse_tnm_triplet(frag)
        if tnm is None:
            continue
        for snomed in snomed_codes:
            result = _engine().resolve_stage(
                cancer_type_snomed=snomed,
                tnm=tnm,
                source="text",
            )
            if result.staging_system != "unknown":
                return _as_dict(result)
    return None


def _try_explicit(text: str) -> dict[str, Any] | None:
    """Try every harvested explicit Stage fragment (e.g. 'Stage IIIA')."""
    for frag in _harvest_explicit(text):
        result = _engine().resolve_stage(
            cancer_type_snomed="",
            explicit_stage=frag,
            source="text",
        )
        if result.staging_system != "unknown":
            return _as_dict(result)
    return None


def _try_non_tnm(text: str) -> dict[str, Any] | None:
    """Try every non-TNM staging-system fragment (FIGO, Ann Arbor, Binet, etc.)."""
    for frag in _harvest_non_tnm(text):
        result = _engine().resolve_stage(
            cancer_type_snomed="",
            explicit_stage=frag,
            source="text",
        )
        if result.staging_system != "unknown":
            return _as_dict(result)
    return None


def _try_descriptive(text: str) -> dict[str, Any] | None:
    """Fallback: 'in situ' -> Stage 0; 'metastatic' -> Stage IV."""
    if _IN_SITU_RE.search(text or ""):
        m = _IN_SITU_RE.search(text)
        return {
            "cancer_stage": "early",
            "cancer_stage_raw": m.group(0),
            "cancer_stage_group": "0",
            "tnm_t": "TIS",
            "tnm_n": "",
            "tnm_m": "",
            "staging_system": "descriptive",
            "staging_source": "text",
            "staging_confidence": 0.6,
        }
    if _METASTATIC_RE.search(text or ""):
        m = _METASTATIC_RE.search(text)
        return {
            "cancer_stage": "late",
            "cancer_stage_raw": m.group(0),
            "cancer_stage_group": "IV",
            "tnm_t": "",
            "tnm_n": "",
            "tnm_m": "M1",
            "staging_system": "descriptive",
            "staging_source": "text",
            "staging_confidence": 0.6,
        }
    return None


def _as_dict(result: Any) -> dict[str, Any]:
    """Convert a StagingResult dataclass to a plain dict."""
    return {
        "cancer_stage": result.cancer_stage,
        "cancer_stage_raw": result.cancer_stage_raw,
        "cancer_stage_group": result.cancer_stage_group,
        "tnm_t": result.tnm_t,
        "tnm_n": result.tnm_n,
        "tnm_m": result.tnm_m,
        "staging_system": result.staging_system,
        "staging_source": result.staging_source,
        "staging_confidence": result.staging_confidence,
    }


def _empty_stage() -> dict[str, Any]:
    """Return a zero-confidence result when no stage phrase was found."""
    return {
        "cancer_stage": "unknown",
        "cancer_stage_raw": "",
        "cancer_stage_group": "",
        "tnm_t": "",
        "tnm_n": "",
        "tnm_m": "",
        "staging_system": "unknown",
        "staging_source": "none",
        "staging_confidence": 0.0,
    }


def resolve_stage_from_text(text: str, cancer_type: str) -> dict[str, Any]:
    """Top-level staging resolution for a cancer episode's post-diagnosis text.

    Priority order:
        1. TNM triplet mapped through the site-specific UICC rule table.
        2. Explicit stage group (``Stage IIIA``, ``stage 4``).
        3. Non-TNM staging system (FIGO, Ann Arbor, Binet, R-ISS...).
        4. Descriptive fallback ("in situ", "metastatic").
        5. Unknown (empty result).
    """
    if not text:
        return _empty_stage()
    snomed_codes = CANCER_TYPE_TO_SNOMED.get(cancer_type, [])
    for strategy in (
        lambda: _try_tnm(text, snomed_codes),
        lambda: _try_explicit(text),
        lambda: _try_non_tnm(text),
        lambda: _try_descriptive(text),
    ):
        result = strategy()
        if result is not None:
            return result
    return _empty_stage()
