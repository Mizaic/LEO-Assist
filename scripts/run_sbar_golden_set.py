#!/usr/bin/env python3
"""Drive SBAROrchestrator over the manually-curated SBAR golden set.

VT-LEO-AI-189 TC-009 reviewer harness, automation half. The runner
substitutes deterministic stubs for the LLM stages, the terminology
evaluator, the source resolver and the Neo4j session, then asserts
structural reviewer_expectations from each fixture YAML. Per-fixture
reports are written under data/sbar-golden-set-reports/<UTC>/ and the
companion review_sbar_golden_set.py walks them for sign-off.

Usage:
    python3 scripts/run_sbar_golden_set.py
    python3 scripts/run_sbar_golden_set.py --only fixture-04
    python3 scripts/run_sbar_golden_set.py --fixtures-dir <path>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

# Make the repo importable when running directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from libs.sbar.events import (  # noqa: E402
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
    BackgroundSourceType,
)
from libs.sbar.source_resolver import (  # noqa: E402
    ResolvedCode,
    ResolvedSituation,
    ResolvedSource,
)


DEFAULT_FIXTURES_DIR = (
    _REPO_ROOT / "data" / "training" / "sbar-golden-set"
)
DEFAULT_REPORTS_ROOT = _REPO_ROOT / "data" / "sbar-golden-set-reports"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def run(self, query: str, **kwargs):
        self.runs.append((query, kwargs))
        return _FakeResult()


class _FakeResult:
    def single(self):
        return None


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    @contextmanager
    def session(self):
        yield self._session


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


@dataclass
class Fixture:
    id: str
    title: str
    path: Path
    raw: dict[str, Any]

    @property
    def stem(self) -> str:
        return self.path.stem


def load_fixture(path: Path) -> Fixture:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level must be a mapping")
    fid = raw.get("id")
    title = raw.get("title", "")
    if not fid:
        raise ValueError(f"{path}: missing 'id'")
    return Fixture(id=str(fid), title=str(title), path=path, raw=raw)


def list_fixtures(fixtures_dir: Path) -> list[Fixture]:
    paths = sorted(p for p in fixtures_dir.glob("fixture-*.yaml"))
    return [load_fixture(p) for p in paths]


# ---------------------------------------------------------------------------
# Building orchestrator inputs from a fixture
# ---------------------------------------------------------------------------


def _resolve_situation_artifact_type(value: str) -> SituationArtifactType:
    """Accept either the enum NAME (e.g. 'referral_request') or VALUE."""
    try:
        return SituationArtifactType[value]
    except KeyError:
        return SituationArtifactType(value)


def _resolve_background_type(value: str) -> BackgroundSourceType:
    try:
        return BackgroundSourceType[value]
    except KeyError:
        return BackgroundSourceType(value)


def build_payload(fixture: Fixture) -> SBARRequestPayload:
    inp = fixture.raw.get("input") or {}
    sit = inp.get("situation") or {}
    artifacts = []
    for a in sit.get("artifacts") or []:
        artifacts.append(
            SBARArtifactRef(
                type=_resolve_situation_artifact_type(a["type"]),
                id=a.get("id"),
                text=a.get("text"),
            )
        )
    background = []
    for b in inp.get("background") or []:
        background.append(
            SBARBackgroundSourceRef(
                type=_resolve_background_type(b["type"]),
                id=b["id"],
            )
        )
    return SBARRequestPayload(
        run_id=f"golden-{fixture.stem}",
        situation=SBARSituationInput(
            patient_id=inp.get("patient_id") or "pat-unknown",
            artifacts=artifacts,
        ),
        background=background,
        guideline_ids=list(inp.get("guideline_ids") or []),
    )


def build_resolved_situation(fixture: Fixture) -> ResolvedSituation:
    rs = fixture.raw.get("resolved_situation") or {}
    return ResolvedSituation(
        patient_id=rs.get("patient_id") or "pat-unknown",
        patient_summary=dict(rs.get("patient_summary") or {}),
        artifacts=list(rs.get("artifacts") or []),
    )


def build_resolved_background(fixture: Fixture) -> list[ResolvedSource]:
    out: list[ResolvedSource] = []
    for r in fixture.raw.get("resolved_background") or []:
        codes = []
        for c in r.get("codes") or []:
            codes.append(
                ResolvedCode(
                    concept_id=str(c.get("concept_id") or ""),
                    term=str(c.get("term") or ""),
                    semantic_tag=c.get("semantic_tag"),
                    assertion=c.get("assertion") or "present",
                    evidence=c.get("evidence"),
                    confidence=c.get("confidence"),
                    source_label=r.get("source_label"),
                    source_id=str(r.get("source_id") or ""),
                )
            )
        out.append(
            ResolvedSource(
                source_label=str(r.get("source_label") or "Encounter"),
                source_id=str(r.get("source_id") or ""),
                text=r.get("text"),
                codes=codes,
                metadata=dict(r.get("metadata") or {}),
            )
        )
    return out


def build_stub_callers(fixture: Fixture) -> tuple[Callable, Callable, Callable]:
    transcript = fixture.raw.get("llm_transcript") or {}
    sit = transcript.get("situation") or {}
    bg = transcript.get("background") or {}
    rec = transcript.get("recommendation") or {}

    async def _situation(*_a, **_kw):
        return {
            "markdown": sit.get("markdown") or "",
            "raw": dict(sit.get("raw") or {}),
            "error": sit.get("error"),
        }

    async def _background(*_a, **_kw):
        return {
            "markdown": bg.get("markdown") or "",
            "raw": dict(bg.get("raw") or {}),
            "error": bg.get("error"),
        }

    async def _recommendation(*_a, **_kw):
        return {
            "markdown": rec.get("markdown") or "",
            "actions": list(rec.get("actions") or []),
            "raw": dict(rec.get("raw") or {}),
            "error": rec.get("error"),
        }

    return _situation, _background, _recommendation


def build_stub_evaluator(fixture: Fixture) -> Callable[..., dict[str, Any]]:
    eva = fixture.raw.get("evaluator_response") or {}
    outage = bool(eva.get("outage"))
    matched = list(eva.get("matched_rules") or [])

    def _evaluate(**_kw):
        if outage:
            raise RuntimeError("evaluator unavailable (golden-set outage stub)")
        return {"matched_rules": matched, "active_version": "golden-set"}

    return _evaluate


# ---------------------------------------------------------------------------
# Orchestrator invocation
# ---------------------------------------------------------------------------


@dataclass
class RunOutcome:
    fixture_id: str
    fixture_path: str
    status: str
    pathway_hints: dict[str, Any]
    errors: list[str]
    actions: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    content: str
    events: list[dict[str, Any]]
    structural_check: "StructuralCheck"


def run_fixture(fixture: Fixture) -> RunOutcome:
    """Execute one fixture deterministically and capture the outcome."""
    # Lazy import keeps the orchestrator stack out of fixture-only flows
    # (e.g. unit tests that just want to validate fixture schema).
    from services.pipeline_worker.app.services import sbar_orchestrator as orch_mod
    from services.pipeline_worker.app.services.sbar_orchestrator import (
        SBAROrchestrator,
    )

    payload = build_payload(fixture)
    situation_caller, background_caller, recommendation_caller = build_stub_callers(
        fixture
    )
    evaluator = build_stub_evaluator(fixture)
    resolved_situation = build_resolved_situation(fixture)
    resolved_background = build_resolved_background(fixture)

    session = _FakeSession()
    client = _FakeClient(session)
    events: list[dict[str, Any]] = []

    def _publish(run_id: str, event: dict[str, Any]) -> None:
        events.append({"run_id": run_id, **event})

    # Patch the source-resolver hooks the orchestrator imports by name.
    orig_resolve_sit = orch_mod.resolve_situation
    orig_resolve_bg = orch_mod.resolve_background_sources
    orch_mod.resolve_situation = lambda _s, _i: resolved_situation
    orch_mod.resolve_background_sources = lambda _s, _r: resolved_background
    try:
        orch = SBAROrchestrator(
            patient_graph_client=client,
            publish_progress=_publish,
            situation_caller=situation_caller,
            background_caller=background_caller,
            recommendation_caller=recommendation_caller,
            evaluator=evaluator,
        )
        result = asyncio.run(orch.run(payload))
    finally:
        orch_mod.resolve_situation = orig_resolve_sit
        orch_mod.resolve_background_sources = orig_resolve_bg

    check = check_structural(fixture, result)

    return RunOutcome(
        fixture_id=fixture.id,
        fixture_path=str(fixture.path),
        status=result.status,
        pathway_hints=dict(result.pathway_hints or {}),
        errors=list(result.errors or []),
        actions=list(result.actions or []),
        rules=list(result.rules or []),
        content=result.content or "",
        events=events,
        structural_check=check,
    )


# ---------------------------------------------------------------------------
# Structural reviewer-expectation checks
# ---------------------------------------------------------------------------


@dataclass
class StructuralCheck:
    overall: str
    failures: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.failures.append(f"{name}: {detail}".rstrip(": "))


def _phrase_present(content: str, expected: Any) -> tuple[bool, str]:
    """Return (matched?, label) for a required-phrase expectation.

    A bare string is matched as a substring (case-sensitive). A list is
    treated as ANY-OF -- the test passes if any one of the alternatives
    is found. The label used for reporting is the literal expectation
    when it is a string, or 'any of [..]' when it is a list. This keeps
    the reviewer-facing output readable while letting fixtures express
    semantic equivalence (e.g. ``["2WW", "two-week wait"]``).
    """
    if isinstance(expected, list):
        ok = any(p in content for p in expected)
        return ok, f"any of {expected!r}"
    return (expected in content, repr(expected))


def _phrase_absent(content: str, expected: Any) -> tuple[bool, str]:
    """Return (absent?, label) for a banned-phrase expectation."""
    if isinstance(expected, list):
        ok = all(p not in content for p in expected)
        return ok, f"none of {expected!r}"
    return (expected not in content, repr(expected))


def check_structural(fixture: Fixture, result) -> StructuralCheck:
    expectations = fixture.raw.get("reviewer_expectations") or {}
    sc = StructuralCheck(overall="pass")

    # Drafts authored ahead of the rule engine being seeded (e.g. NG12
    # backfill) declare draft: true at the top level. We still parse the
    # reviewer expectations so the structural shape is documented for the
    # reviewer, but we do not fail the run on missing rule output.
    if bool(fixture.raw.get("draft")):
        sc.overall = "draft"
        sc.checks.append({
            "name": "fixture marked draft",
            "ok": True,
            "detail": "structural assertions skipped until rule engine is seeded",
        })
        return sc

    content = result.content or ""

    for heading in expectations.get("required_section_headings") or []:
        sc.record(
            f"section heading present: {heading!r}",
            heading in content,
            "not found in composed content",
        )

    assessment_md = result.assessment or ""
    for phrase in expectations.get("required_phrases_in_assessment") or []:
        ok, label = _phrase_present(assessment_md, phrase)
        sc.record(
            f"assessment contains: {label}",
            ok,
            "missing from Assessment section",
        )

    rec_md = result.recommendation or ""
    for phrase in expectations.get("required_phrases_in_recommendation") or []:
        ok, label = _phrase_present(rec_md, phrase)
        sc.record(
            f"recommendation contains: {label}",
            ok,
            "missing from Recommendation section",
        )

    for phrase in expectations.get("banned_phrases") or []:
        ok, label = _phrase_absent(content, phrase)
        sc.record(
            f"banned phrase absent: {label}",
            ok,
            "appears anywhere in composed SBAR content",
        )

    hints = result.pathway_hints or {}
    expected_hints = expectations.get("expected_pathway_hints") or {}
    if "rtr" in expected_hints:
        sc.record(
            f"pathway_hints.rtr == {expected_hints['rtr']!r}",
            hints.get("rtr") == expected_hints["rtr"],
            f"got {hints.get('rtr')!r}",
        )
    if "rtr_evidence_contains" in expected_hints:
        substr = expected_hints["rtr_evidence_contains"]
        ev = hints.get("rtr_evidence") or ""
        sc.record(
            f"rtr_evidence contains {substr!r}",
            substr in ev,
            f"actual: {ev!r}",
        )
    if "stt_contains" in expected_hints:
        substr = expected_hints["stt_contains"]
        stt = hints.get("stt") or ""
        sc.record(
            f"stt contains {substr!r}",
            substr.lower() in stt.lower(),
            f"actual: {stt!r}",
        )
    if "stt_evidence_contains" in expected_hints:
        substr = expected_hints["stt_evidence_contains"]
        ev = hints.get("stt_evidence") or ""
        sc.record(
            f"stt_evidence contains {substr!r}",
            substr in ev,
            f"actual: {ev!r}",
        )
    if expected_hints.get("stt_is_null"):
        sc.record(
            "stt is null",
            hints.get("stt") in (None, ""),
            f"actual: {hints.get('stt')!r}",
        )

    if "expected_action_priority" in expectations:
        target = expectations["expected_action_priority"]
        priorities = [a.get("priority") for a in result.actions or []]
        sc.record(
            f"recommendation has at least one action with priority={target!r}",
            target in priorities,
            f"actions: {priorities!r}",
        )

    if "expected_status" in expectations:
        sc.record(
            f"final SBAR status == {expectations['expected_status']!r}",
            result.status == expectations["expected_status"],
            f"actual: {result.status!r}",
        )

    if "expected_errors_contain" in expectations:
        needle = expectations["expected_errors_contain"]
        joined = "\n".join(result.errors or [])
        sc.record(
            f"errors[] contains {needle!r}",
            needle in joined,
            f"errors: {result.errors!r}",
        )

    if sc.failures:
        sc.overall = "fail"
    return sc


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_report(reports_dir: Path, fixture: Fixture, outcome: RunOutcome) -> Path:
    fixture_dir = reports_dir / fixture.stem
    fixture_dir.mkdir(parents=True, exist_ok=True)

    # Echo of the fixture (so reviewers can audit without leaving the
    # report directory).
    (fixture_dir / "fixture.yaml").write_text(
        yaml.safe_dump(fixture.raw, sort_keys=False)
    )

    # Composed Markdown SBAR.
    (fixture_dir / "output.md").write_text(outcome.content)

    # Pathway hints.
    (fixture_dir / "pathway_hints.json").write_text(
        json.dumps(outcome.pathway_hints, indent=2, sort_keys=True)
    )

    # Recorded actions + matched rules + errors.
    (fixture_dir / "result.json").write_text(
        json.dumps(
            {
                "fixture_id": outcome.fixture_id,
                "fixture_path": outcome.fixture_path,
                "status": outcome.status,
                "errors": outcome.errors,
                "actions": outcome.actions,
                "rules": outcome.rules,
            },
            indent=2,
            sort_keys=True,
        )
    )

    # Per-stage progress events.
    with (fixture_dir / "events.jsonl").open("w") as fh:
        for ev in outcome.events:
            fh.write(json.dumps(ev, sort_keys=True) + "\n")

    # Structural check verdict.
    (fixture_dir / "structural_check.json").write_text(
        json.dumps(
            {
                "overall": outcome.structural_check.overall,
                "failures": outcome.structural_check.failures,
                "checks": outcome.structural_check.checks,
            },
            indent=2,
            sort_keys=True,
        )
    )

    return fixture_dir


def write_run_summary(
    reports_dir: Path,
    outcomes: list[RunOutcome],
) -> Path:
    summary_path = reports_dir / "run_summary.json"
    summary = {
        "generated_at": _now_stamp(),
        "fixture_count": len(outcomes),
        "structural_pass_count": sum(
            1 for o in outcomes if o.structural_check.overall == "pass"
        ),
        "structural_draft_count": sum(
            1 for o in outcomes if o.structural_check.overall == "draft"
        ),
        "fixtures": [
            {
                "fixture_id": o.fixture_id,
                "fixture_path": o.fixture_path,
                "structural_status": o.structural_check.overall,
                "failures": o.structural_check.failures,
                "sbar_status": o.status,
                "errors": o.errors,
            }
            for o in outcomes
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _select(fixtures: list[Fixture], only: Iterable[str] | None) -> list[Fixture]:
    if not only:
        return fixtures
    keep = set(only)
    out = [f for f in fixtures if f.stem in keep or f.id in keep]
    if not out:
        raise SystemExit(f"No fixtures matched: {sorted(keep)!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-dir",
        default=str(DEFAULT_FIXTURES_DIR),
        help=(
            "Directory containing fixture-*.yaml "
            "(default: data/training/sbar-golden-set)"
        ),
    )
    parser.add_argument(
        "--reports-dir",
        default=None,
        help=(
            "Override the reports output directory "
            "(default: data/sbar-golden-set-reports/<UTC stamp>)"
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Run only the named fixture(s); may be repeated. Accepts file stem or id.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit non-zero on the first structural-check failure.",
    )
    args = parser.parse_args(argv)

    fixtures_dir = Path(args.fixtures_dir).resolve()
    fixtures = _select(list_fixtures(fixtures_dir), args.only)

    if args.reports_dir:
        reports_dir = Path(args.reports_dir).resolve()
    else:
        reports_dir = DEFAULT_REPORTS_ROOT / _now_stamp()
    reports_dir.mkdir(parents=True, exist_ok=True)

    # The orchestrator deliberately logs.exception when a stage fails so
    # production operators can see it. In the golden-set runner we EXPECT
    # the evaluator-outage fixture to fail Stage 3, so we mute the
    # orchestrator's logger to keep the report output readable.
    logging.getLogger(
        "services.pipeline_worker.app.services.sbar_orchestrator"
    ).setLevel(logging.CRITICAL)

    outcomes: list[RunOutcome] = []
    failures = 0
    for fixture in fixtures:
        print(f"-- {fixture.id}: {fixture.title}")
        outcome = run_fixture(fixture)
        write_report(reports_dir, fixture, outcome)
        outcomes.append(outcome)
        verdict = outcome.structural_check.overall
        print(f"   structural: {verdict}")
        if verdict != "pass":
            failures += 1
            for fline in outcome.structural_check.failures:
                print(f"     - {fline}")
            if args.fail_fast:
                break

    summary_path = write_run_summary(reports_dir, outcomes)
    print(f"Reports written to: {reports_dir}")
    print(f"Summary: {summary_path}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
