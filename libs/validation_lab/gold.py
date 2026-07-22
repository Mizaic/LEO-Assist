"""Unified gold contract and scoring for Validation Lab.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DI-9138BAC9

Every field here has an honest real-pipeline readback source (see
`libs/validation_lab/pipeline.py::read_real_outputs`):
  - snomed_codes    <- Assessment.assessment_codes
  - matching_rules  <- Assessment.assessment_rules
  - completeness    <- Assessment.completeness_result_json
  - sbar_*          <- Assessment.id / Assessment.content

There is intentionally no "entities" field -- the real pipeline does
not persist a structured entity readback on Assessment today, so
scoring against one would be ungrounded. Add it back only once a real
readback exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from libs.validation_lab.models import PersistMode


@dataclass
class GoldContract:
    snomed_codes: list[str] = field(default_factory=list)
    completeness: dict[str, Any] = field(default_factory=dict)
    matching_rules: list[str] = field(default_factory=list)
    sbar_assessment_id: str = ""
    sbar_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> GoldContract:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            snomed_codes=[str(x) for x in (raw.get("snomed_codes") or [])],
            completeness=dict(raw.get("completeness") or {}),
            matching_rules=[str(x) for x in (raw.get("matching_rules") or [])],
            sbar_assessment_id=str(raw.get("sbar_assessment_id") or ""),
            sbar_markdown=str(raw.get("sbar_markdown") or ""),
        )


@dataclass
class RunOutputs:
    snomed_codes: list[str] = field(default_factory=list)
    completeness: dict[str, Any] = field(default_factory=dict)
    matching_rules: list[str] = field(default_factory=list)
    sbar_assessment_id: str = ""
    sbar_markdown: str = ""
    phase_outputs: list[dict[str, Any]] = field(default_factory=list)
    # Real Assessment telemetry only -- never invent spend figures.
    llm_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> RunOutputs:
        if not isinstance(raw, dict):
            return cls()
        usage = raw.get("llm_usage") or {}
        return cls(
            snomed_codes=[str(x) for x in (raw.get("snomed_codes") or [])],
            completeness=dict(raw.get("completeness") or {}),
            matching_rules=[str(x) for x in (raw.get("matching_rules") or [])],
            sbar_assessment_id=str(raw.get("sbar_assessment_id") or ""),
            sbar_markdown=str(raw.get("sbar_markdown") or ""),
            phase_outputs=list(raw.get("phase_outputs") or []),
            llm_usage=dict(usage) if isinstance(usage, dict) else {},
        )

    def as_gold(self) -> GoldContract:
        return GoldContract(
            snomed_codes=list(self.snomed_codes),
            completeness=dict(self.completeness),
            matching_rules=list(self.matching_rules),
            sbar_assessment_id=self.sbar_assessment_id,
            sbar_markdown=self.sbar_markdown,
        )


def promote_blocked_reason(persist_mode: str | PersistMode) -> str | None:
    """Return error text when gold promote is not allowed."""
    mode = (
        persist_mode.value
        if isinstance(persist_mode, PersistMode)
        else str(persist_mode or "")
    )
    if mode != PersistMode.production.value:
        return (
            "Save as gold is only allowed after a production-persist Lab run. "
            "Dry-run cannot promote gold."
        )
    return None


def _set_equal(a: list[str], b: list[str]) -> bool:
    return set(x.strip().lower() for x in a if x.strip()) == set(
        x.strip().lower() for x in b if x.strip()
    )


def score_against_gold(
    gold: GoldContract | dict[str, Any],
    outputs: RunOutputs | dict[str, Any],
) -> dict[str, Any]:
    """Score run outputs against gold. Empty gold groups are skipped."""
    g = gold if isinstance(gold, GoldContract) else GoldContract.from_dict(gold)
    o = outputs if isinstance(outputs, RunOutputs) else RunOutputs.from_dict(outputs)
    groups: dict[str, Any] = {}
    if g.snomed_codes:
        groups["snomed_codes"] = {
            "pass": _set_equal(g.snomed_codes, o.snomed_codes),
            "expected": g.snomed_codes,
            "actual": o.snomed_codes,
        }
    if g.completeness:
        groups["completeness"] = {
            "pass": g.completeness == o.completeness,
            "expected": g.completeness,
            "actual": o.completeness,
        }
    if g.matching_rules:
        groups["matching_rules"] = {
            "pass": _set_equal(g.matching_rules, o.matching_rules),
            "expected": g.matching_rules,
            "actual": o.matching_rules,
        }
    if g.sbar_assessment_id or g.sbar_markdown:
        id_ok = (not g.sbar_assessment_id) or (
            g.sbar_assessment_id == o.sbar_assessment_id
        )
        md_ok = (not g.sbar_markdown) or (
            g.sbar_markdown.strip() == o.sbar_markdown.strip()
        )
        groups["sbar"] = {
            "pass": id_ok and md_ok,
            "expected_assessment_id": g.sbar_assessment_id,
            "actual_assessment_id": o.sbar_assessment_id,
        }
    if not groups:
        return {"pass": True, "groups": {}, "message": "no gold fields set"}
    overall = all(bool(v.get("pass")) for v in groups.values())
    return {"pass": overall, "groups": groups}
