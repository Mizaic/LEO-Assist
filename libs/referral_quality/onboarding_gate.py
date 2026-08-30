"""Teach a form, run its golden letter, and report the go-live gate.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.pipeline.form_coverage import measure_form_coverage
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import dict_to_section
from libs.pipeline.form_schema_store import remember_schema
from libs.pipeline.form_section_hits import collect_section_hits
from libs.referral_quality.contamination import (
    ContaminationHit,
    find_contaminated_facts,
)
from libs.referral_quality.golden_corpus import (
    ExpectedFact,
    GoldenCase,
    load_golden_case,
)
from libs.referral_quality.slot_fill_eval import invented_facts

_GATE_CHECKS = (
    "coverage",
    "completeness assessability",
    "assertion invariants",
    "contamination",
    "sbar invariants",
    "invented facts",
)
_VALID_ASSERTIONS = frozenset(
    {
        "present",
        "absent",
        "negated",
        "refuted",
        "family",
        "hypothetical",
        "possible",
        "assertion_unverified",
    }
)


@dataclass
class GateReport:
    ready: bool
    coverage_incomplete: bool
    completeness_assessable: bool
    contamination: list[ContaminationHit]
    checks: list[str]
    errors: list[str] = field(default_factory=list)


def load_taught_form(path: Path) -> tuple[FormSchema, list[dict[str, Any]]]:
    """Load a taught form JSON and remember it in the process cache."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("form schema must be an object")
    sections = [dict_to_section(item) for item in raw.get("sections") or []]
    groups = raw.get("completeness_groups") or []
    taught = list(groups) if isinstance(groups, list) else []
    schema = FormSchema(
        schema_id=str(raw.get("fingerprint") or "taught"),
        fingerprint=str(raw.get("fingerprint") or ""),
        form_name=str(raw.get("form_name") or ""),
        sections=sections,
        created_by="onboarding",
        organization_id=str(raw.get("organization_id") or ""),
        service_id=str(raw.get("service_id") or ""),
        prompt_contract=bool(raw.get("prompt_contract")),
        completeness_groups=taught,
    )
    remember_schema(schema)
    return schema, taught


def evaluate_onboarding(
    case_dir: Path,
    extra_facts: list[dict[str, Any]] | None = None,
    headline: str = "",
) -> GateReport:
    """Run coverage, contamination and assertion checks for one golden letter."""
    case = load_golden_case(case_dir)
    schema, groups = load_taught_form(case.form_schema_path)
    return _gate_report(case, schema, groups, extra_facts, headline)


def _gate_report(
    case: GoldenCase,
    schema: FormSchema,
    groups: list[dict[str, Any]],
    extra_facts: list[dict[str, Any]] | None,
    headline: str,
) -> GateReport:
    coverage = measure_form_coverage(schema, [case.letter])
    hits = collect_section_hits(schema, [case.letter])
    completeness = evaluate_completeness_groups(
        groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assessable = not bool(completeness.get("degraded"))
    facts = _facts_for_gate(case, extra_facts)
    contamination = find_contaminated_facts(facts, schema, case.letter)
    errors = _collect_errors(
        coverage_incomplete=coverage.incomplete,
        assessable=assessable,
        expected_assessable=case.completeness.assessable,
        contamination=contamination,
        facts=facts,
        case=case,
        headline=headline,
    )
    if invented_facts(facts, case.letter):
        errors.append("invented facts")
    return GateReport(
        ready=not errors,
        coverage_incomplete=coverage.incomplete,
        completeness_assessable=assessable,
        contamination=contamination,
        checks=_GATE_CHECKS,
        errors=errors,
    )


def run_onboarding(case_dir: Path) -> int:
    """Return 0 when the golden letter is ready to go live."""
    return 0 if evaluate_onboarding(case_dir).ready else 1


def _facts_for_gate(
    case: GoldenCase,
    extra_facts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    facts = [_fact_dict(item) for item in case.expected_facts]
    facts.extend(item for item in extra_facts or [] if isinstance(item, dict))
    return facts


def _fact_dict(item: ExpectedFact) -> dict[str, Any]:
    return {
        "text": item.text,
        "assertion": item.assertion,
        "evidence_text": item.evidence_text or item.text,
    }


def _collect_errors(
    *,
    coverage_incomplete: bool,
    assessable: bool,
    expected_assessable: bool,
    contamination: list[ContaminationHit],
    facts: list[dict[str, Any]],
    case: GoldenCase,
    headline: str,
) -> list[str]:
    errors: list[str] = []
    if coverage_incomplete:
        errors.append("coverage incomplete")
    if not assessable or (expected_assessable and not assessable):
        errors.append("completeness not assessable")
    if contamination:
        errors.append("contamination")
    if not _assertions_ok(facts):
        errors.append("assertion missing")
    errors.extend(_sbar_errors(case, headline))
    return errors


def _assertions_ok(facts: list[dict[str, Any]]) -> bool:
    for fact in facts:
        assertion = str(fact.get("assertion") or "").strip().lower()
        if assertion not in _VALID_ASSERTIONS:
            return False
    return True


def _sbar_errors(case: GoldenCase, headline: str) -> list[str]:
    if not headline.strip():
        return []
    lower = headline.lower()
    errors: list[str] = []
    for needle in case.sbar.headline_must_contain:
        if needle.lower() not in lower:
            errors.append(f"sbar missing {needle}")
    for needle in case.sbar.headline_must_not_contain:
        if needle.lower() in lower:
            errors.append(f"sbar leaked {needle}")
    return errors
