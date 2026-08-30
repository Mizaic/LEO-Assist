"""Resolve soft guideline words to confirmed, not_confirmed, or contradicted.

Body site is not a soft word. Enforcement (soft vs hard) lives in the
caller, not here.

Atlas:
  DI-DE8B125E, DI-0C904503
  Look up via: get_design_control(dc_type="design_input", dc_id=...)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SOFT_QUALIFIER_KINDS = frozenset(
    {
        "first_presentation",
        "repeat_or_chronic",
        "unexplained",
        "unintentional",
        "persistent",
    }
)
RECENCY_DAYS = frozenset({30, 90, 180, 365, 730, 1825})
SoftOutcome = Literal["confirmed", "not_confirmed", "contradicted"]

_PHRASES: dict[str, tuple[str, ...]] = {
    "first_presentation": (
        "first episode",
        "first presentation",
        "never had this before",
        "never had this",
        "first time",
    ),
    "unexplained": ("unexplained",),
    "unintentional": ("unintentional",),
    "persistent": ("persistent", "persisting"),
    "repeat_or_chronic": ("recurrent", "repeat", "chronic"),
}


INVESTIGATION_POLICIES = frozenset({"required", "not_required", "result_gate"})
ENFORCEMENT_MODES = frozenset({"soft", "hard"})


class SoftQualifierError(ValueError):
    """Closed-set or window validation failed."""


class SoftQualifierSpec(BaseModel):
    """Wire shape for one soft check on a CONCEPT chip."""

    model_config = {"extra": "forbid"}

    kind: str
    enforcement: str = "soft"
    concept_id: str | None = None
    max_occurrences: int | None = Field(default=None, ge=0)
    min_occurrences: int | None = Field(default=None, ge=1)
    within_days: int | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in SOFT_QUALIFIER_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(SOFT_QUALIFIER_KINDS)}; got {v!r}."
            )
        return v

    @field_validator("enforcement")
    @classmethod
    def _check_enforcement(cls, v: str) -> str:
        if v not in ENFORCEMENT_MODES:
            raise ValueError(
                f"enforcement must be one of {sorted(ENFORCEMENT_MODES)}; got {v!r}."
            )
        return v

    @field_validator("within_days")
    @classmethod
    def _check_within_days(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if int(v) not in RECENCY_DAYS:
            raise ValueError(
                f"within_days must be one of {sorted(RECENCY_DAYS)}; got {v!r}."
            )
        return int(v)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _letter_text(patient_facts: dict[str, Any] | None) -> str:
    if not patient_facts:
        return ""
    return str(patient_facts.get("letter_text") or "").lower()


def _word_hit(phrase: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(phrase)}\b", text))


def _phrase_hit(kind: str, letter: str) -> bool:
    return any(_word_hit(phrase, letter) for phrase in _PHRASES.get(kind, ()))


_TERM_STOP = frozenset({"of", "the", "a", "an", "and", "or", "from"})


def _finding_tokens(term: str) -> tuple[str, ...]:
    cleaned = re.sub(r"\([^)]*\)", "", term or "").lower()
    return tuple(
        tok
        for tok in re.findall(r"[a-z]+", cleaned)
        if tok not in _TERM_STOP and len(tok) > 2
    )


def _clauses(letter: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.\n|;]+", letter) if part.strip()]


def _repeat_or_chronic_of_finding(letter: str, term: str) -> bool:
    """True when recurrent/repeat/chronic modifies this finding, not form chrome."""
    tokens = _finding_tokens(term)
    if not tokens:
        return _phrase_hit("repeat_or_chronic", letter)
    for clause in _clauses(letter):
        if not any(
            _word_hit(phrase, clause) for phrase in _PHRASES["repeat_or_chronic"]
        ):
            continue
        if any(token in clause for token in tokens):
            return True
    return False


def _older_than_window(
    qualifier: dict[str, Any],
    patient_facts: dict[str, Any] | None,
    now: datetime,
) -> bool:
    """True when the same concept appears on the record older than the window."""
    concept_id = str(qualifier.get("concept_id") or "").strip()
    within_days = qualifier.get("within_days")
    if within_days is None:
        within_days = 90
    if not concept_id:
        return False
    if int(within_days) not in RECENCY_DAYS:
        raise SoftQualifierError(
            f"within_days must be one of {sorted(RECENCY_DAYS)}; got {within_days!r}."
        )
    facts = patient_facts or {}
    occurrences = (facts.get("concept_occurrences") or {}).get(concept_id)
    if not occurrences:
        return False
    cutoff = _as_utc(now) - timedelta(days=int(within_days))
    for raw in occurrences:
        if not isinstance(raw, datetime):
            continue
        if _as_utc(raw) < cutoff:
            return True
    return False


def _count_in_window(
    qualifier: dict[str, Any],
    patient_facts: dict[str, Any] | None,
    now: datetime,
) -> int | None:
    concept_id = str(qualifier.get("concept_id") or "").strip()
    within_days = qualifier.get("within_days")
    if not concept_id or within_days is None:
        return None
    if int(within_days) not in RECENCY_DAYS:
        raise SoftQualifierError(
            f"within_days must be one of {sorted(RECENCY_DAYS)}; got {within_days!r}."
        )
    facts = patient_facts or {}
    occurrences = (facts.get("concept_occurrences") or {}).get(concept_id)
    if occurrences is None:
        return None
    cutoff = _as_utc(now) - timedelta(days=int(within_days))
    count = 0
    for raw in occurrences:
        if not isinstance(raw, datetime):
            continue
        if _as_utc(raw) >= cutoff:
            count += 1
    return count


def resolve_soft_qualifier(
    qualifier: dict[str, Any],
    patient_facts: dict[str, Any] | None,
    now: datetime,
) -> SoftOutcome:
    """Return confirmed, not_confirmed, or contradicted for one soft word."""
    kind = str((qualifier or {}).get("kind") or "").strip()
    if kind in {"body_site", "site"}:
        raise SoftQualifierError("body site is not a soft kind")
    if kind not in SOFT_QUALIFIER_KINDS:
        raise SoftQualifierError(f"unknown soft kind: {kind!r}")

    count = _count_in_window(qualifier, patient_facts, now)
    max_occ = qualifier.get("max_occurrences")
    if count is not None and max_occ is not None and count > int(max_occ):
        return "contradicted"
    min_occ = qualifier.get("min_occurrences")
    if count is not None and min_occ is not None and count >= int(min_occ):
        return "confirmed"
    letter = _letter_text(patient_facts)
    if kind == "first_presentation":
        if _repeat_or_chronic_of_finding(letter, str(qualifier.get("term") or "")):
            return "contradicted"
        if _older_than_window(qualifier, patient_facts, now):
            return "contradicted"
        return "confirmed"
    if _phrase_hit(kind, letter):
        return "confirmed"
    return "not_confirmed"


def apply_soft_qualifiers(
    node: dict[str, Any],
    patient_facts: dict[str, Any] | None,
    now: datetime,
    unverified: list[str],
) -> bool:
    """Return True when the CONCEPT leaf may still fire.

    Soft not_confirmed still allows the leaf and appends the kind.
    Contradicted, or hard plus not_confirmed, blocks the leaf.
    """
    try:
        resolver = resolve_soft_qualifier
    except Exception as exc:  # pragma: no cover - import is local
        raise SoftQualifierError("resolver unavailable") from exc
    criterion = dict(node.get("criterion") or {})
    default_concept = str(criterion.get("snomed_concept_id") or "")
    default_term = str(criterion.get("preferred_term") or "")
    for raw in criterion.get("soft_qualifiers") or []:
        spec = dict(raw) if isinstance(raw, dict) else {}
        if not spec.get("concept_id"):
            spec["concept_id"] = default_concept
        if not spec.get("term"):
            spec["term"] = default_term
        outcome = resolver(spec, patient_facts, now)
        if outcome == "contradicted":
            return False
        if outcome != "not_confirmed":
            continue
        if spec.get("enforcement") == "hard":
            return False
        unverified.append(str(spec.get("kind") or ""))
    return True


def fit_is_present(
    patient_codes: list[str] | None,
    observations: list[dict[str, Any]] | None,
) -> bool:
    """True when a FIT kit or result code is already on the record."""
    from libs.guidelines.investigation_family import FIT_FAMILY_IDS, patient_fact_ids

    return bool(patient_fact_ids(patient_codes, observations) & FIT_FAMILY_IDS)


def status_for_policy(policy: str | None, fit_present: bool) -> str | None:
    """Per-rule investigation status for a faecal immunochemical test policy."""
    if not policy:
        return None
    if policy == "not_required":
        return "exempt"
    if policy in {"required", "result_gate"}:
        return "offered_or_resulted" if fit_present else "missing"
    return None


def overall_investigation_status(statuses: list[str | None]) -> str | None:
    """Mass-bypass (exempt) wins when any matched rule is not_required."""
    present = [s for s in statuses if s]
    if "exempt" in present:
        return "exempt"
    if "missing" in present:
        return "missing"
    if "offered_or_resulted" in present:
        return "offered_or_resulted"
    return None
