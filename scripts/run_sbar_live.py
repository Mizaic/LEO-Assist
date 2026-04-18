#!/usr/bin/env python3
"""One-shot live LLM run of the SBAR golden-set fixtures.

This is the "wet" complement to ``run_sbar_golden_set.py``. Where the
golden-set runner stubs the LLM with each fixture's recorded transcript,
this script calls the real Bedrock/Azure-OpenAI model for every fixture
using the same in-code factory-default prompts the orchestrator would
seed into Neo4j.

The goal is to surface real-world drift in the prompt hardening rules:
source attribution, conflict surfacing, no-inference, prompt-injection
resistance, British English, reading-age, etc.

The Assessment stage is still deterministic (we feed the canned
``evaluator_response.matched_rules`` straight into
``libs.sbar.assessment_formatter.format_assessment``) so this run is
LLM-only for Situation, Background and Recommendation.

Usage:
    python3 scripts/run_sbar_live.py
    python3 scripts/run_sbar_live.py --only fixture-07 --only fixture-08
    python3 scripts/run_sbar_live.py --reports-dir /tmp/sbar-live

Requires AWS Bedrock (or Azure OpenAI) credentials in the environment
(see ``secrets/.env.secrets``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    if not path.exists():
        return
    import os

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(_REPO_ROOT / "secrets" / ".env.secrets")
_load_env_file(_REPO_ROOT / "secrets" / ".env.config")


from libs.prompts.sbar_situation_v1 import SBAR_SITUATION_SYSTEM_V1  # noqa: E402
from libs.prompts.sbar_background_v1 import SBAR_BACKGROUND_SYSTEM_V1  # noqa: E402
from libs.prompts.sbar_recommendation_v1 import (  # noqa: E402
    SBAR_RECOMMENDATION_SYSTEM_V1,
)
from libs.sbar.assessment_formatter import format_assessment  # noqa: E402
from libs.sbar.prompt_calls import (  # noqa: E402
    call_background,
    call_recommendation,
    call_situation,
)

from scripts.run_sbar_golden_set import (  # noqa: E402
    DEFAULT_FIXTURES_DIR,
    Fixture,
    StructuralCheck,
    _phrase_absent,
    _phrase_present,
    build_resolved_background,
    build_resolved_situation,
    list_fixtures,
)
from libs.sbar.source_resolver import aggregate_codes  # noqa: E402


DEFAULT_REPORTS_ROOT = _REPO_ROOT / "data" / "sbar-live-reports"


_PROMPT_OVERRIDES = {
    "sbar_situation": SBAR_SITUATION_SYSTEM_V1,
    "sbar_background": SBAR_BACKGROUND_SYSTEM_V1,
    "sbar_recommendation": SBAR_RECOMMENDATION_SYSTEM_V1,
}


def _local_prompt(name: str) -> str:
    """Skip Neo4j; use the in-code factory default for the live run."""
    if name not in _PROMPT_OVERRIDES:
        raise KeyError(name)
    return _PROMPT_OVERRIDES[name]


# ---------------------------------------------------------------------------
# Per-stage live invocation
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    name: str
    markdown: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class LiveOutcome:
    fixture_id: str
    fixture_path: str
    stages: list[StageResult]
    pathway_hints: dict[str, Any]
    rules: list[dict[str, Any]]
    composed: str
    structural: StructuralCheck


def _compose(
    situation_md: str,
    background_md: str,
    assessment_md: str,
    recommendation_md: str,
) -> str:
    return (
        "## Situation\n\n"
        f"{situation_md.strip()}\n\n"
        "## Background\n\n"
        f"{background_md.strip()}\n\n"
        "## Assessment\n\n"
        f"{assessment_md.strip()}\n\n"
        "## Recommendation\n\n"
        f"{recommendation_md.strip()}\n"
    )


async def _run_one_live(fixture: Fixture) -> LiveOutcome:
    payload_input = fixture.raw.get("input") or {}
    resolved_situation = build_resolved_situation(fixture)
    resolved_background = build_resolved_background(fixture)
    aggregated_codes = aggregate_codes(resolved_background)
    referring_specialty = None
    for art in resolved_situation.artifacts or []:
        if art.get("referring_specialty"):
            referring_specialty = art["referring_specialty"]
            break

    stages: list[StageResult] = []

    # 1. Situation
    t0 = time.time()
    sit = await call_situation(
        resolved_situation,
        patient_id=resolved_situation.patient_id,
        prompt_fetcher=_local_prompt,
    )
    stages.append(
        StageResult(
            name="situation",
            markdown=sit.get("markdown") or "",
            raw=sit.get("raw") or {},
            error=sit.get("error"),
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    )

    # 2. Background
    t0 = time.time()
    bg = await call_background(
        resolved_background,
        aggregated_codes,
        referring_specialty=referring_specialty,
        patient_id=resolved_situation.patient_id,
        prompt_fetcher=_local_prompt,
    )
    stages.append(
        StageResult(
            name="background",
            markdown=bg.get("markdown") or "",
            raw=bg.get("raw") or {},
            error=bg.get("error"),
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    )

    # 3. Assessment (deterministic; uses canned matched_rules).
    # Mirror SBAROrchestrator's outage branch when the fixture asks for
    # one, so the live run is structurally indistinguishable from the
    # offline run for the evaluator-outage fixture (fixture-05).
    eva_response = fixture.raw.get("evaluator_response") or {}
    matched_rules = list(eva_response.get("matched_rules") or [])
    patient_code_ids = [c.concept_id for c in aggregated_codes]
    assessment_error: str | None = None
    if eva_response.get("outage"):
        from libs.sbar.assessment_formatter import AssessmentNarrative

        outage_msg = "evaluator unavailable (live-run outage stub)"
        assessment_narrative = AssessmentNarrative(
            markdown="_Assessment unavailable due to evaluator error._",
            rules=[],
            codes=patient_code_ids,
            pathway_hints={
                "stt": None,
                "stt_evidence": None,
                "alternative_pathway": None,
                "alternative_pathway_evidence": None,
                "rtr": "no",
                "rtr_evidence": outage_msg,
            },
        )
        assessment_error = f"assessment:{outage_msg}"
    else:
        assessment_narrative = format_assessment(
            matched_rules=matched_rules,
            patient_codes=patient_code_ids,
            guideline_ids=list(payload_input.get("guideline_ids") or []),
        )
    stages.append(
        StageResult(
            name="assessment",
            markdown=assessment_narrative.markdown,
            raw={"rules": assessment_narrative.rules},
            error=assessment_error,
            elapsed_ms=0,
        )
    )

    # 4. Recommendation
    guideline_titles = sorted(
        {
            r.get("guideline_title") or ""
            for r in matched_rules
            if r.get("guideline_title")
        }
    )
    t0 = time.time()
    rec = await call_recommendation(
        situation_md=stages[0].markdown,
        background_md=stages[1].markdown,
        assessment_md=stages[2].markdown,
        assessment_rules=assessment_narrative.rules,
        guideline_titles=guideline_titles,
        guidelines=list(payload_input.get("guideline_ids") or []),
        patient_id=resolved_situation.patient_id,
        prompt_fetcher=_local_prompt,
    )
    stages.append(
        StageResult(
            name="recommendation",
            markdown=rec.get("markdown") or "",
            actions=list(rec.get("actions") or []),
            raw=rec.get("raw") or {},
            error=rec.get("error"),
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    )

    composed = _compose(
        stages[0].markdown,
        stages[1].markdown,
        stages[2].markdown,
        stages[3].markdown,
    )

    structural = _check_structural(
        fixture,
        composed=composed,
        assessment_md=stages[2].markdown,
        recommendation_md=stages[3].markdown,
        actions=stages[3].actions,
        pathway_hints=assessment_narrative.pathway_hints,
        errors=[s.error for s in stages if s.error],
    )

    return LiveOutcome(
        fixture_id=fixture.id,
        fixture_path=str(fixture.path),
        stages=stages,
        pathway_hints=assessment_narrative.pathway_hints,
        rules=assessment_narrative.rules,
        composed=composed,
        structural=structural,
    )


# ---------------------------------------------------------------------------
# Same structural-check rules as the offline runner, but applied to the
# LIVE composed SBAR rather than the canned transcripts.
# ---------------------------------------------------------------------------


def _check_structural(
    fixture: Fixture,
    *,
    composed: str,
    assessment_md: str,
    recommendation_md: str,
    actions: list[dict[str, Any]],
    pathway_hints: dict[str, Any],
    errors: list[str | None],
) -> StructuralCheck:
    expectations = fixture.raw.get("reviewer_expectations") or {}
    sc = StructuralCheck(overall="pass")

    for heading in expectations.get("required_section_headings") or []:
        sc.record(
            f"section heading present: {heading!r}",
            heading in composed,
            "not found in composed content",
        )

    req_assess = expectations.get("required_phrases_in_assessment") or []
    for phrase in req_assess:
        ok, label = _phrase_present(assessment_md, phrase)
        sc.record(
            f"assessment contains: {label}",
            ok,
            "missing from Assessment section",
        )

    for phrase in expectations.get("required_phrases_in_recommendation") or []:
        ok, label = _phrase_present(recommendation_md, phrase)
        sc.record(
            f"recommendation contains: {label}",
            ok,
            "missing from Recommendation section",
        )

    for phrase in expectations.get("banned_phrases") or []:
        ok, label = _phrase_absent(composed, phrase)
        sc.record(
            f"banned phrase absent: {label}",
            ok,
            "appears anywhere in composed SBAR content",
        )

    expected_hints = expectations.get("expected_pathway_hints") or {}
    if "rtr" in expected_hints:
        sc.record(
            f"pathway_hints.rtr == {expected_hints['rtr']!r}",
            pathway_hints.get("rtr") == expected_hints["rtr"],
            f"got {pathway_hints.get('rtr')!r}",
        )
    if "stt_contains" in expected_hints:
        substr = expected_hints["stt_contains"]
        stt = pathway_hints.get("stt") or ""
        sc.record(
            f"stt contains {substr!r}",
            substr.lower() in stt.lower(),
            f"actual: {stt!r}",
        )
    if expected_hints.get("stt_is_null"):
        sc.record(
            "stt is null",
            pathway_hints.get("stt") in (None, ""),
            f"actual: {pathway_hints.get('stt')!r}",
        )

    if "expected_action_priority" in expectations:
        target = expectations["expected_action_priority"]
        priorities = [a.get("priority") for a in actions]
        sc.record(
            f"recommendation has at least one action with priority={target!r}",
            target in priorities,
            f"actions: {priorities!r}",
        )

    real_errors = [e for e in errors if e]
    expected_err = expectations.get("expected_errors_contain")
    if expected_err is not None:
        joined = "\n".join(real_errors)
        sc.record(
            f"errors[] contains {expected_err!r}",
            expected_err in joined,
            f"errors: {real_errors!r}",
        )
    elif real_errors:
        sc.record(
            "no unexpected stage errors",
            False,
            f"errors: {real_errors!r}",
        )

    if sc.failures:
        sc.overall = "fail"
    return sc


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_report(reports_dir: Path, fixture: Fixture, outcome: LiveOutcome) -> None:
    fixture_dir = reports_dir / fixture.stem
    fixture_dir.mkdir(parents=True, exist_ok=True)

    (fixture_dir / "fixture.yaml").write_text(
        yaml.safe_dump(fixture.raw, sort_keys=False)
    )
    (fixture_dir / "live_output.md").write_text(outcome.composed)
    (fixture_dir / "pathway_hints.json").write_text(
        json.dumps(outcome.pathway_hints, indent=2, sort_keys=True)
    )
    (fixture_dir / "structural_check.json").write_text(
        json.dumps(
            {
                "overall": outcome.structural.overall,
                "failures": outcome.structural.failures,
                "checks": outcome.structural.checks,
            },
            indent=2,
            sort_keys=True,
        )
    )
    (fixture_dir / "stages.json").write_text(
        json.dumps(
            [
                {
                    "name": s.name,
                    "elapsed_ms": s.elapsed_ms,
                    "error": s.error,
                    "markdown": s.markdown,
                    "actions": s.actions,
                    "raw": s.raw,
                }
                for s in outcome.stages
            ],
            indent=2,
        )
    )


def _write_summary(
    reports_dir: Path, outcomes: list[LiveOutcome]
) -> Path:
    path = reports_dir / "live_summary.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": _now_stamp(),
                "fixture_count": len(outcomes),
                "structural_pass_count": sum(
                    1 for o in outcomes if o.structural.overall == "pass"
                ),
                "fixtures": [
                    {
                        "fixture_id": o.fixture_id,
                        "structural_status": o.structural.overall,
                        "failures": o.structural.failures,
                        "stage_errors": [
                            {"stage": s.name, "error": s.error}
                            for s in o.stages
                            if s.error
                        ],
                        "stage_latency_ms": {
                            s.name: s.elapsed_ms for s in o.stages
                        },
                    }
                    for o in outcomes
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-dir", default=str(DEFAULT_FIXTURES_DIR),
    )
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument(
        "--only", action="append", default=None,
        help="Run only the named fixture(s); may be repeated.",
    )
    args = parser.parse_args(argv)

    fixtures = list_fixtures(Path(args.fixtures_dir).resolve())
    if args.only:
        keep = set(args.only)
        fixtures = [f for f in fixtures if f.stem in keep or f.id in keep]
        if not fixtures:
            print(f"No fixtures matched: {sorted(keep)!r}", file=sys.stderr)
            return 2

    reports_dir = (
        Path(args.reports_dir).resolve()
        if args.reports_dir
        else DEFAULT_REPORTS_ROOT / _now_stamp()
    )
    reports_dir.mkdir(parents=True, exist_ok=True)

    outcomes: list[LiveOutcome] = []
    for fx in fixtures:
        print(f"-- {fx.id}: {fx.title}", flush=True)
        try:
            outcome = asyncio.run(_run_one_live(fx))
        except Exception as exc:
            print(f"   FAILED to invoke live stack: {exc!r}")
            continue
        _write_report(reports_dir, fx, outcome)
        outcomes.append(outcome)
        print(f"   structural: {outcome.structural.overall}")
        for fline in outcome.structural.failures:
            print(f"     - {fline}")
        latencies = {s.name: s.elapsed_ms for s in outcome.stages}
        print(f"   latency_ms: {latencies}")

    summary_path = _write_summary(reports_dir, outcomes)
    print(f"Reports written to: {reports_dir}")
    print(f"Summary: {summary_path}")
    fails = sum(1 for o in outcomes if o.structural.overall != "pass")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
