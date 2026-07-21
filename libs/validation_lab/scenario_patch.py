"""ScenarioPatch / ScenarioVariant contracts for Validation Lab brainstorm.

Atlas: DI-EB716E68 / DO-A0ADDB38

Wire contract uses camelCase keys shared with the UI. verify_patch strips
unverified SNOMED / observable / equity values. normalise_variants enforces
per-recommendation caps (3 positives each) or a freeform cap of 5, plus
at most 1 control, and router ownership of expectedTrigger.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from libs.validation_lab.equity_taxonomy import (
    comorbidity_band_options,
    ethnicity_concept_ids,
    is_valid_core20_decile,
    performance_status_grades,
    plus_group_options,
)
from libs.validation_lab.scenario_catalog import (
    derive_summary,
    derive_tags,
    is_placeholder_title,
)

VARIANTS_PER_RECOMMENDATION = 3
FREEFORM_POSITIVE_CAP = 5
MAX_CONTROL_VARIANTS = 1

PlusGroup = Literal[
    "ethnic_minority_community",
    "coastal_deprivation_community",
    "learning_disability_or_autism",
    "inclusion_health_group",
    "none",
]
ComorbidityBand = Literal["none", "low", "moderate", "high"]
PmhCategory = Literal["condition", "medication", "allergy"]


class EquityBlock(BaseModel):
    """Optional synthetic-only equity fields on a scenario variant."""

    model_config = ConfigDict(extra="ignore")

    ethnicityConceptId: str | None = None
    ethnicityTerm: str | None = None
    performanceStatusGrade: int | None = None
    comorbidityBand: ComorbidityBand | None = None
    core20Decile: int | None = None
    plusGroup: PlusGroup | None = None


class ObservationTrigger(BaseModel):
    """Numeric lab-value trigger for GuidelineEvaluator observations."""

    model_config = ConfigDict(extra="ignore")

    observableId: str
    value: float
    unit: str


class PmhRow(BaseModel):
    """One PMH suggestion row."""

    model_config = ConfigDict(extra="ignore")

    category: PmhCategory
    conceptId: str
    term: str = ""


class ScenarioPatch(BaseModel):
    """Fields that may be applied into the New Test Patient wizard."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    patientName: str | None = None
    patientAge: str | None = None
    patientSex: str | None = None
    caseType: Literal["referral"] | None = None
    pmh: list[PmhRow] | None = None
    observations: list[ObservationTrigger] | None = None
    referralText: str | None = None
    equity: EquityBlock | None = None


class ScenarioVariant(ScenarioPatch):
    """One proposed test-patient variant card."""

    variantId: str
    targetRecId: str | None = None
    label: str
    rationale: str
    recommended: bool = False
    triggerConceptIds: list[str] = Field(default_factory=list)
    isControl: bool = False
    expectedTrigger: bool | None = None
    expectedTriggerReason: str | None = None

    @field_validator("patientSex")
    @classmethod
    def _sex_ok(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if value not in ("male", "female", "other"):
            raise ValueError("patientSex must be male|female|other|empty")
        return value


def _strip_equity(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    cid = str(raw.get("ethnicityConceptId") or "").strip()
    if cid and cid in ethnicity_concept_ids():
        out["ethnicityConceptId"] = cid
        term = str(raw.get("ethnicityTerm") or "").strip()
        if term:
            out["ethnicityTerm"] = term
    grade = raw.get("performanceStatusGrade")
    try:
        grade_i = int(grade) if grade is not None else None
    except (TypeError, ValueError):
        grade_i = None
    if grade_i is not None and grade_i in performance_status_grades():
        out["performanceStatusGrade"] = grade_i
    band = str(raw.get("comorbidityBand") or "").strip()
    if band in comorbidity_band_options():
        out["comorbidityBand"] = band
    decile = raw.get("core20Decile")
    try:
        decile_i = int(decile) if decile is not None else None
    except (TypeError, ValueError):
        decile_i = None
    if is_valid_core20_decile(decile_i):
        out["core20Decile"] = decile_i
    plus = str(raw.get("plusGroup") or "").strip()
    if plus in plus_group_options():
        out["plusGroup"] = plus
    return out or None


def verify_patch(
    raw_patch: dict[str, Any] | None,
    seen_concepts: dict[str, Any] | set[str] | None,
    seen_observables: set[str] | None = None,
) -> dict[str, Any]:
    """Strip unverified concept/observable/equity values from a raw patch."""
    patch = dict(raw_patch or {})
    concept_ids = (
        set(seen_concepts.keys())
        if isinstance(seen_concepts, dict)
        else set(seen_concepts or ())
    )
    observable_ids = set(seen_observables or ())

    if "pmh" in patch:
        kept: list[dict[str, Any]] = []
        for row in patch.get("pmh") or []:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("conceptId") or "").strip()
            if not cid or cid not in concept_ids:
                continue
            kept.append(
                {
                    "category": row.get("category") or "condition",
                    "conceptId": cid,
                    "term": str(row.get("term") or "").strip(),
                }
            )
        patch["pmh"] = kept

    if "triggerConceptIds" in patch:
        patch["triggerConceptIds"] = [
            str(cid).strip()
            for cid in (patch.get("triggerConceptIds") or [])
            if str(cid).strip() in concept_ids
        ]

    if "observations" in patch:
        obs_kept: list[dict[str, Any]] = []
        for row in patch.get("observations") or []:
            if not isinstance(row, dict):
                continue
            oid = str(row.get("observableId") or "").strip()
            if not oid or oid not in observable_ids:
                continue
            try:
                value = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            unit = str(row.get("unit") or "").strip()
            if not unit:
                continue
            obs_kept.append({"observableId": oid, "value": value, "unit": unit})
        patch["observations"] = obs_kept

    if "equity" in patch:
        patch["equity"] = _strip_equity(patch.get("equity"))

    return patch


def _pick(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def coerce_variant_wire(raw: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Normalise LLM/tool variant dicts to camelCase wire fields with defaults.

    Models often emit snake_case or omit label/variantId. Without stable ids
    the UI renders blank cards and every checkbox shares key=undefined.
    """
    row = dict(raw)
    variant_id = str(_pick(row, "variantId", "variant_id", default="") or "").strip()
    if not variant_id:
        variant_id = f"variant-{index + 1}"
    label = str(_pick(row, "label", "name", "title", default="") or "").strip()
    title = str(
        _pick(row, "title", "caseTitle", "case_title", default="") or ""
    ).strip()
    rationale = str(_pick(row, "rationale", "reason", "why", default="") or "").strip()
    if not rationale:
        rationale = "Proposed as a representative test-patient variant."
    summary = derive_summary(row, rationale)
    tags = derive_tags(row)
    if is_placeholder_title(title):
        title = ""
    if is_placeholder_title(label):
        label = ""
    if not title:
        title = label or summary[:80] or f"Variant {index + 1}"
    if not label:
        label = title
    if not summary:
        summary = rationale[:200]

    out = dict(row)
    out["variantId"] = variant_id
    out["label"] = label
    out["title"] = title
    out["summary"] = summary
    out["tags"] = tags
    out["rationale"] = rationale
    out["targetRecId"] = _pick(row, "targetRecId", "target_rec_id", default=None)
    out["recommended"] = bool(_pick(row, "recommended", default=False))
    out["isControl"] = bool(_pick(row, "isControl", "is_control", default=False))
    out["patientName"] = _pick(row, "patientName", "patient_name", default=None)
    out["patientAge"] = _pick(row, "patientAge", "patient_age", default=None)
    if out["patientAge"] is not None:
        out["patientAge"] = str(out["patientAge"])
    out["patientSex"] = _pick(row, "patientSex", "patient_sex", default=None)
    out["referralText"] = _pick(row, "referralText", "referral_text", default=None)
    out["triggerConceptIds"] = list(
        _pick(row, "triggerConceptIds", "trigger_concept_ids", default=[]) or []
    )
    if "expectedTrigger" not in out and "expected_trigger" in row:
        out["expectedTrigger"] = row.get("expected_trigger")
    if "expectedTriggerReason" not in out and "expected_trigger_reason" in row:
        out["expectedTriggerReason"] = row.get("expected_trigger_reason")
    return out


def _ensure_one_recommended(group: list[dict[str, Any]]) -> None:
    if not group:
        return
    if not any(bool(v.get("recommended")) for v in group):
        group[0]["recommended"] = True
    seen = False
    for row in group:
        if bool(row.get("recommended")):
            if seen:
                row["recommended"] = False
            else:
                seen = True
                row["recommended"] = True


def normalise_variants(
    variants: list[dict[str, Any]] | None,
    *,
    rule_evaluated: bool = False,
    per_rec_cap: int = VARIANTS_PER_RECOMMENDATION,
    freeform_cap: int = FREEFORM_POSITIVE_CAP,
) -> list[dict[str, Any]]:
    """Cap positives per targetRecId (or freeform total) + at most one control."""
    by_rec: dict[str, list[dict[str, Any]]] = {}
    freeform: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for index, raw in enumerate(variants or []):
        if not isinstance(raw, dict):
            continue
        row = coerce_variant_wire(raw, index=index)
        if not rule_evaluated:
            row["expectedTrigger"] = None
        if bool(row.get("isControl")):
            row["recommended"] = False
            if len(controls) < MAX_CONTROL_VARIANTS:
                controls.append(row)
            continue
        row["isControl"] = False
        target = str(row.get("targetRecId") or "").strip()
        if target:
            bucket = by_rec.setdefault(target, [])
            if len(bucket) < int(per_rec_cap):
                bucket.append(row)
            continue
        if len(freeform) < int(freeform_cap):
            freeform.append(row)

    positives: list[dict[str, Any]] = []
    for group in by_rec.values():
        _ensure_one_recommended(group)
        positives.extend(group)
    _ensure_one_recommended(freeform)
    positives.extend(freeform)
    return positives + controls
