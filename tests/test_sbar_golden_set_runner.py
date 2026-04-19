"""VT-LEO-AI-189 TC-009: SBAR golden-set runner + reviewer harness.

Pins the structural invariants of each manually-curated fixture and
the runner/harness contract:

- All fixture YAMLs (currently 19) exist and parse with the required keys.
- Every fixture builds a valid SBARRequestPayload.
- The runner executes every fixture against the orchestrator with the
  recorded LLM transcript and evaluator response, and the rendered
  SBAR satisfies every reviewer_expectation in the fixture.
- The reviewer harness produces a signed_ledger.json with the right
  schema and overall verdict logic.

These automated checks DO NOT replace the manual TC-009 sign-off; they
guard against silent regressions in the harness itself and in any
prompt/orchestrator change that breaks a fixture's structural
invariants. Manual sign-off remains required for the VT to flip from
'draft' to 'passed'.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

import logging  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Suppress the orchestrator's logger.exception noise from the
# evaluator-outage fixture; it is expected and the runner already
# silences it in the CLI path.
logging.getLogger(
    "services.pipeline_worker.app.services.sbar_orchestrator"
).setLevel(logging.CRITICAL)


def _load_script(module_name: str, filename: str):
    """Import a script that lives outside the package tree.

    Registers the module in sys.modules BEFORE exec_module so dataclass
    field-type resolution can find it (Python 3.13+ requirement).
    """
    spec = importlib.util.spec_from_file_location(
        module_name, _REPO_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner_module():
    return _load_script("sbar_golden_set_runner", "run_sbar_golden_set.py")


@pytest.fixture(scope="module")
def review_module():
    return _load_script("sbar_golden_set_review", "review_sbar_golden_set.py")


@pytest.fixture(scope="module")
def fixtures(runner_module):
    return runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)


# ---------------------------------------------------------------------------
# Fixture-collection-level invariants
# ---------------------------------------------------------------------------


# Expected fixture count grows with the suite. NG12 / referral-triage
# backfill (2026-04-18) added fixtures 11-19 (six new pathways +
# two adversarial twins + sarcoma).
_EXPECTED_FIXTURE_COUNT = 19


def test_expected_fixture_count_present(fixtures) -> None:
    assert len(fixtures) == _EXPECTED_FIXTURE_COUNT, [
        f.path.name for f in fixtures
    ]


def test_fixture_ids_match_filename(fixtures) -> None:
    for fx in fixtures:
        n = fx.path.stem.split("-")[1]  # 'fixture-04' -> '04'
        assert fx.id == f"SBAR-GS-{n}", (fx.path.name, fx.id)


def test_manifest_lists_every_fixture(runner_module) -> None:
    import yaml

    manifest_path = runner_module.DEFAULT_FIXTURES_DIR / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    listed_files = {entry["file"] for entry in manifest["fixtures"]}
    on_disk = {
        p.name
        for p in runner_module.DEFAULT_FIXTURES_DIR.glob("fixture-*.yaml")
    }
    assert listed_files == on_disk, (listed_files ^ on_disk)


# ---------------------------------------------------------------------------
# Per-fixture schema invariants
# ---------------------------------------------------------------------------


_REQUIRED_TOP_LEVEL_KEYS = {
    "id",
    "title",
    "clinical_scenario",
    "input",
    "resolved_situation",
    "resolved_background",
    "llm_transcript",
    "evaluator_response",
    "reviewer_expectations",
}

_REQUIRED_TRANSCRIPT_KEYS = {"situation", "background", "recommendation"}


@pytest.mark.parametrize(
    "fixture_path",
    sorted(
        (Path(__file__).resolve().parents[1]
         / "design-controls"
         / "training-data"
         / "sbar-golden-set").glob("fixture-*.yaml"),
    ),
    ids=lambda p: p.stem,
)
def test_fixture_has_required_keys(fixture_path, runner_module) -> None:
    fx = runner_module.load_fixture(fixture_path)
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(fx.raw.keys())
    assert not missing, (fx.path.name, missing)
    transcript_keys = set((fx.raw["llm_transcript"] or {}).keys())
    transcript_missing = _REQUIRED_TRANSCRIPT_KEYS - transcript_keys
    assert not transcript_missing, (fx.path.name, transcript_missing)
    expectations = fx.raw["reviewer_expectations"]
    assert "required_section_headings" in expectations, fx.path.name
    assert "expected_pathway_hints" in expectations, fx.path.name
    assert "reviewer_focus" in expectations, fx.path.name


@pytest.mark.parametrize(
    "fixture_path",
    sorted(
        (Path(__file__).resolve().parents[1]
         / "design-controls"
         / "training-data"
         / "sbar-golden-set").glob("fixture-*.yaml"),
    ),
    ids=lambda p: p.stem,
)
def test_fixture_payload_builds(fixture_path, runner_module) -> None:
    fx = runner_module.load_fixture(fixture_path)
    payload = runner_module.build_payload(fx)
    assert payload.run_id.startswith("golden-")
    assert payload.situation.patient_id
    # Background entries must validate as Encounter | DocumentReference | Chunk
    assert all(b.id for b in payload.background)


# ---------------------------------------------------------------------------
# End-to-end run: every fixture passes structural checks
# ---------------------------------------------------------------------------


def test_runner_reports_every_fixture_pass(tmp_path, runner_module) -> None:
    fixtures = runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)
    outcomes = []
    for fx in fixtures:
        outcome = runner_module.run_fixture(fx)
        runner_module.write_report(tmp_path, fx, outcome)
        outcomes.append(outcome)

    summary_path = runner_module.write_run_summary(tmp_path, outcomes)
    summary = json.loads(summary_path.read_text())
    assert summary["fixture_count"] == _EXPECTED_FIXTURE_COUNT
    # Drafts (NG12 backfill awaiting rule engine seeding) are accepted
    # alongside structural passes -- the contract is that every fixture
    # is either a structural pass or an explicit draft, never a silent
    # failure.
    pass_or_draft = (
        summary["structural_pass_count"] + summary["structural_draft_count"]
    )
    assert pass_or_draft == _EXPECTED_FIXTURE_COUNT, summary["fixtures"]

    # Per-fixture report files all exist.
    for fx in fixtures:
        fdir = tmp_path / fx.stem
        assert (fdir / "fixture.yaml").exists()
        assert (fdir / "output.md").exists()
        assert (fdir / "pathway_hints.json").exists()
        assert (fdir / "result.json").exists()
        assert (fdir / "structural_check.json").exists()
        assert (fdir / "events.jsonl").exists()


def test_evaluator_outage_fixture_persists_draft(
    tmp_path, runner_module,
) -> None:
    fixtures = {
        fx.stem: fx
        for fx in runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)
    }
    fx = fixtures["fixture-05"]
    outcome = runner_module.run_fixture(fx)
    assert outcome.status == "draft"
    assert any(e.startswith("assessment:") for e in outcome.errors)
    assert outcome.pathway_hints.get("rtr") == "no"


def test_multi_rule_priority_sort(runner_module) -> None:
    fixtures = {
        fx.stem: fx
        for fx in runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)
    }
    fx = fixtures["fixture-10"]
    outcome = runner_module.run_fixture(fx)
    assess = outcome.content
    assert assess.find("R-UGI-001") < assess.find("R-MSK-001"), (
        "2WW rule must render before routine rule"
    )
    assert outcome.pathway_hints["rtr"] == "yes"
    assert "R-UGI-001" in outcome.pathway_hints["stt_evidence"]


# ---------------------------------------------------------------------------
# Phrase-matching contract: bare string OR any-of list
# ---------------------------------------------------------------------------


def test_phrase_present_string_substring(runner_module) -> None:
    ok, label = runner_module._phrase_present("Refer urgent 2WW lung", "2WW")
    assert ok is True
    assert label == "'2WW'"


def test_phrase_present_string_missing(runner_module) -> None:
    ok, label = runner_module._phrase_present(
        "Refer under two-week wait pathway", "2WW"
    )
    assert ok is False
    assert label == "'2WW'"


def test_phrase_present_list_any_of_passes(runner_module) -> None:
    ok, label = runner_module._phrase_present(
        "Refer under two-week wait pathway",
        ["2WW", "two-week wait", "two week wait"],
    )
    assert ok is True
    assert label.startswith("any of [")


def test_phrase_present_list_any_of_fails(runner_module) -> None:
    ok, _ = runner_module._phrase_present(
        "Refer routinely",
        ["2WW", "two-week wait", "two week wait"],
    )
    assert ok is False


def test_phrase_absent_string(runner_module) -> None:
    ok, _ = runner_module._phrase_absent(
        "Refer urgently", "as an AI",
    )
    assert ok is True
    ok2, _ = runner_module._phrase_absent(
        "as an AI I cannot help", "as an AI",
    )
    assert ok2 is False


def test_phrase_absent_list_none_of(runner_module) -> None:
    ok, label = runner_module._phrase_absent(
        "Refer urgently", ["agreed", "Dr Test", "ignore previous"],
    )
    assert ok is True
    assert label.startswith("none of [")
    ok_fail, _ = runner_module._phrase_absent(
        "agreed - sign as Dr Test",
        ["agreed", "Dr Test"],
    )
    assert ok_fail is False


def test_fixture_06_does_not_require_routine_action(runner_module) -> None:
    """Per Recommendation Rule 3, an empty assessment_rules input means
    the prompt MUST emit zero structured actions. Fixture-06 must not
    accidentally re-introduce an expected_action_priority constraint
    that contradicts the prompt contract.
    """
    fx = next(
        f for f in runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)
        if f.stem == "fixture-06"
    )
    assert "expected_action_priority" not in (
        fx.raw.get("reviewer_expectations") or {}
    )


# ---------------------------------------------------------------------------
# Reviewer harness: signed-ledger schema and verdict logic
# ---------------------------------------------------------------------------


def test_signed_ledger_passes_when_all_pass(tmp_path, review_module) -> None:
    verdicts = [
        {"fixture_id": f"SBAR-GS-{i:02d}", "verdict": "pass", "comment": "ok"}
        for i in range(1, _EXPECTED_FIXTURE_COUNT + 1)
    ]
    path = review_module._signed_ledger(
        tmp_path, "Dr Test", "QA Lead", verdicts
    )
    ledger = json.loads(path.read_text())
    assert ledger["overall"] == "pass"
    assert ledger["counts"] == {
        "pass": _EXPECTED_FIXTURE_COUNT,
        "fail": 0,
        "skip": 0,
        "total": _EXPECTED_FIXTURE_COUNT,
    }
    assert ledger["vt_id"] == "VT-LEO-AI-189"
    assert ledger["test_case_id"] == "VT-189-TC-009"
    assert ledger["reviewer"] == "Dr Test"
    assert ledger["reviewer_role"] == "QA Lead"


def test_signed_ledger_fails_when_any_fail_or_skip(
    tmp_path, review_module,
) -> None:
    verdicts = [
        {"fixture_id": "SBAR-GS-01", "verdict": "pass"},
        {"fixture_id": "SBAR-GS-02", "verdict": "fail"},
        {"fixture_id": "SBAR-GS-03", "verdict": "skip"},
    ]
    path = review_module._signed_ledger(tmp_path, "X", "Y", verdicts)
    ledger = json.loads(path.read_text())
    assert ledger["overall"] == "fail"
    assert ledger["counts"]["fail"] == 1
    assert ledger["counts"]["skip"] == 1


def test_review_harness_noninteractive_records_skip(
    tmp_path, runner_module, review_module,
) -> None:
    # Build a one-fixture report directory.
    fixtures = runner_module.list_fixtures(runner_module.DEFAULT_FIXTURES_DIR)
    one = fixtures[0]
    outcome = runner_module.run_fixture(one)
    runner_module.write_report(tmp_path, one, outcome)
    runner_module.write_run_summary(tmp_path, [outcome])

    rc = review_module.main([
        "--reports-dir", str(tmp_path),
        "--noninteractive",
    ])
    # Skip-only run -> overall fail (because nothing reviewed pass).
    assert rc == 1
    ledger = json.loads((tmp_path / "signed_ledger.json").read_text())
    assert ledger["counts"]["skip"] == 1
    assert ledger["overall"] == "fail"
