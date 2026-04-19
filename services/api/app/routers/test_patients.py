"""HTTP surface for the persistent test-patient library.

Mounted under ``/guidance/test-patients`` (the proxy at /api/* exposes
this to the browser).  All endpoints require the ai.admin role.

Endpoints:
  POST   /guidance/test-patients/dry-run     -- preview without saving
  POST   /guidance/test-patients             -- save (after dry-run)
  GET    /guidance/test-patients             -- list with scope filter
  GET    /guidance/test-patients/{id}        -- detail
  PATCH  /guidance/test-patients/{id}        -- update profile + expectations
  DELETE /guidance/test-patients/{id}
  POST   /guidance/test-patients/generate    -- auto-generate happy/fail/boundary
  POST   /guidance/test-patients/replay      -- regression replay
  GET    /guidance/test-patients/replay-reports        -- list reports
  GET    /guidance/test-patients/replay-reports/{id}   -- one report
  GET    /guidance/test-patients/guidelines  -- scope picker helper
  GET    /guidance/test-patients/rules       -- rule picker helper
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.deps import require_admin, require_admin_or_service
from app.services import (
    test_patient_clone,
    test_patient_generator,
    test_patient_scaffolder,
    test_patient_scenario_scaffolder,
    test_patient_service,
)
from app.services.test_patient_clone import CloneError
from app.services.test_patient_redactor import get_default_redactor
from app.services.test_patient_scaffolder import ScaffoldError
from app.services.test_patient_scenario_scaffolder import (
    ScenarioScaffoldError,
)
from app.services.test_patient_service import EditorError, PatientPayload
from libs.auth.org_scope import CallerScope
from libs.cypher.test_patient_queries import TEST_PATIENT_ASPECTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance", tags=["test-patients"])


def _client() -> CodingGraphClient:
    """Knowledge graph client (where TestPatient nodes live)."""
    return CodingGraphClient()


def _patient_client() -> PatientGraphClient:
    """Patient graph client (where real :Patient nodes live)."""
    return PatientGraphClient()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PatientBody(BaseModel):
    codes: list[str] = Field(default_factory=list)
    age: float | None = None
    sex: Literal["male", "female", "other"] | None = None
    pathway_id: str | None = None
    name: str = ""
    description: str = ""
    generation_source: str = "manual"

    def to_payload(self) -> PatientPayload:
        return PatientPayload(
            codes=self.codes,
            age=self.age,
            sex=self.sex,
            pathway_id=self.pathway_id,
            name=self.name,
            description=self.description,
            generation_source=self.generation_source,
        )


class DryRunRequest(BaseModel):
    patient: PatientBody
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None


class ExpectationBody(BaseModel):
    rule_id: str
    fires: bool
    matched_branch_node_ids: list[str] = Field(default_factory=list)


class SaveRequest(BaseModel):
    patient: PatientBody
    guideline_id: str
    expectations: list[ExpectationBody] = Field(default_factory=list)
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    skip_if_exists: bool = True


class UpdateRequest(BaseModel):
    """Body for ``PATCH /test-patients/{id}``.

    The reviewer is editing a saved patient.  The full new profile +
    expectation list is supplied -- the service rewrites both
    atomically (DELETE existing EXPECTED_RESULT rels, then write the
    new ones), so the saved patient ends up exactly as described
    here. Empty ``expectations`` is allowed (the patient ends up
    with no assertions, which makes replay a no-op for that row).
    """

    patient: PatientBody
    expectations: list[ExpectationBody] = Field(default_factory=list)
    ruleset_version: str | None = None


class GenerateRequest(BaseModel):
    scope_type: Literal["rule", "branch", "guideline", "all"] = "guideline"
    guideline_id: str | None = None
    rule_id: str | None = None
    branch_node_id: str | None = None
    depth: Literal["minimal_pair", "boundary_plus_pairs"] = "boundary_plus_pairs"
    exclude_existing: bool = True


class DiagnoseRequest(BaseModel):
    """Request body for per-rule diagnostic evaluation."""

    rule_id: str
    patient: PatientBody
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None


class ReplayRequest(BaseModel):
    patient_ids: list[str] | None = None
    guideline_id: str | None = None
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    persist_report: bool = True


class CloneFromRealRequest(BaseModel):
    """Body for ``POST /test-patients/clone``.

    Copies a real :Patient subgraph to a new :TestPatient, removes
    identifiable details and tags the new record with the supplied
    aspect. Per DI-59824215 / R-8C0CC94B (Atlas) the resulting node
    always carries a "test_" display-name prefix and an `is_test = true`
    flag. The original real patient is never modified.
    """

    source_patient_id: str
    aspect: Literal["nlp", "episodes", "guidelines", "summarisation"]
    description: str = ""


class EditorCodeBody(BaseModel):
    """One expected SNOMED code attached to an editor encounter."""

    concept_id: str
    term: str | None = None
    assertion: Literal[
        "present", "absent", "history_of", "suspected", "uncertain"
    ] = "present"


class EditorEncounterBody(BaseModel):
    """One encounter as edited in the per-aspect drawer.

    The editor surfaces a small, plain-English form per encounter:
    a free-text note, an optional date and source label, and the
    expected SNOMED codes the AI should pick out of that note. Codes
    are MERGE'd against pre-loaded :Concept nodes -- the service
    layer fails loudly when a code is missing from the knowledge
    graph (mirrors the cross-graph clone guarantee).
    """

    id: str | None = None
    source_label: str | None = None
    source_id: str | None = None
    date: str | None = None
    text: str = ""
    codes: list[EditorCodeBody] = Field(default_factory=list)


class EditorExpectedSbarBody(BaseModel):
    """Expected SBAR transcript for the summarisation aspect."""

    id: str | None = None
    fixture_id: str | None = None
    situation_md: str = ""
    background_md: str = ""
    recommendation_md: str = ""
    matched_rule_ids: list[str] = Field(default_factory=list)
    required_phrases: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    expected_action_priority: str | None = None
    reviewer_focus: str = ""
    evaluator_outage: bool = False


class EditorFullUpdateBody(BaseModel):
    """Body for ``PATCH /test-patients/{id}/full``.

    The editor sends the entire editable subgraph in one shot. The
    service rewrites the encounter list (and, for summarisation, the
    expected SBAR) atomically; old children are detached and replaced
    so the saved subgraph matches the body exactly.

    Guidelines aspect is rejected at this entry point and must use
    ``PATCH /test-patients/{id}`` instead so the rule-fire snapshot
    is preserved.
    """

    aspect: Literal["nlp", "episodes", "summarisation"]
    name: str
    description: str = ""
    age: float | None = None
    sex: Literal["male", "female", "other"] | None = None
    encounters: list[EditorEncounterBody] = Field(default_factory=list)
    expected_sbar: EditorExpectedSbarBody | None = None


class BuildBlankRequest(BaseModel):
    """Body for ``POST /test-patients/build``.

    Used by the Knowledge > Test Patients > Build dialog when the
    selected aspect is NLP, Episodes or Summarisation. Creates an
    empty :TestPatient row with just demographics; the per-aspect
    content (free text + expected codes / expected episode timeline /
    expected SBAR) is attached in a follow-up step.

    For aspect = "guidelines" the dialog routes through the existing
    ``POST /test-patients`` endpoint instead, which also snapshots
    expected rule fires.
    """

    aspect: Literal["nlp", "episodes", "summarisation"]
    name: str
    description: str = ""
    age: float | None = None
    sex: Literal["male", "female", "other"] | None = None


class SandboxReplayRequest(BaseModel):
    """Compile UNSAVED draft rules and replay saved patients against them.

    Used by the rule editor's "Test against library" button. The compile
    is written to a custom-scoped key so it cannot collide with the
    production ruleset, and the sandbox is dropped automatically once
    the replay returns (with a Redis TTL fallback in case the cleanup
    request never lands).
    """

    rules: list[dict] = Field(default_factory=list)
    patient_ids: list[str] | None = None
    guideline_id: str | None = None
    sandbox_id: str | None = None
    policy_mode: Literal["advisory", "strict"] = "advisory"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/test-patients/dry-run")
def dry_run(
    body: DryRunRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Evaluate a patient against the live ruleset without saving."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.dry_run(
            client,
            body.patient.to_payload(),
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        client.close()


@router.post("/test-patients/diagnose")
def diagnose_rule(
    body: DiagnoseRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Return per-node match diagnostics for ONE rule against a patient.

    The diagnostic verdict is computed by the same bitmap evaluator that
    production uses to fire rules, so the per-leaf annotations are
    guaranteed to agree with the live firing decision.
    """
    _ = scope
    try:
        return test_patient_service.diagnose_rule_against_patient(
            body.patient.to_payload(),
            rule_id=body.rule_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/test-patients")
def save_patient(
    body: SaveRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Save a test patient + snapshot expectations.  Idempotent by hash."""
    client = _client()
    try:
        return test_patient_service.confirm_and_save(
            client,
            body.patient.to_payload(),
            [exp.model_dump() for exp in body.expectations],
            guideline_id=body.guideline_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            created_by=getattr(scope, "user_email", "") or "unknown",
            ruleset_version=body.ruleset_version,
            skip_if_exists=body.skip_if_exists,
        )
    finally:
        client.close()


@router.get("/test-patients")
def list_patients(
    aspect: str | None = Query(
        default=None,
        description=(
            "Filter by AI aspect. One of nlp / episodes / guidelines / "
            "summarisation, or 'all' / omitted to return every aspect."
        ),
    ),
    guideline_id: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
    triage_outcome: str | None = Query(
        default=None,
        description=(
            "Filter SBAR / referral-triage patients by the derived "
            "outcome. One of 2ww / urgent / routine / no_rule_fired / "
            "evaluator_outage / unset, or 'all' / omitted for no filter."
        ),
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Return all saved patients matching the scope filter."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_patients(
            client,
            aspect=aspect,
            guideline_id=guideline_id,
            rule_id=rule_id,
            node_id=node_id,
            triage_outcome=triage_outcome,
            limit=limit,
        )
    finally:
        client.close()


@router.get("/test-patients/aspect-counts")
def get_aspect_counts(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, int]:
    """Return counts per aspect for the four count tiles.

    Always returns one entry per known aspect (zero when there are no
    patients for it) plus a synthetic "all" total. The Knowledge tab
    uses this to render a stable four-tile layout.
    """
    _ = scope
    client = _client()
    try:
        return test_patient_service.count_by_aspect(client)
    finally:
        client.close()


@router.get("/test-patients/triage-outcome-counts")
def get_triage_outcome_counts(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, int]:
    """Return counts per triage outcome for the SBAR aspect chip group.

    Always returns one entry per known outcome (zero when none) so the
    UI can render a stable chip group without conditional logic. Only
    counts SBAR / referral-triage patients -- the other aspects do not
    have an ExpectedSBAR node and so do not have a triage outcome.
    """
    _ = scope
    client = _client()
    try:
        return test_patient_service.count_by_triage_outcome(client)
    finally:
        client.close()


@router.get("/test-patients/source-patients")
def list_source_patients(
    limit: int = Query(default=50, ge=1, le=500),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Return real patients available as a clone source.

    Reads from the **patient graph** (where real :Patient nodes live).
    Filters out :TestPatient rows so only true production patients
    appear. Used by the Knowledge > Test Patients > Clone-from-real
    dialog.
    """
    _ = scope
    patient_graph = _patient_client()
    try:
        return test_patient_clone.list_source_patients(
            patient_graph, limit=limit
        )
    finally:
        patient_graph.close()


@router.post("/test-patients/clone")
def clone_from_real_patient(
    body: CloneFromRealRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Copy a real patient to a new de-identified :TestPatient.

    Cross-graph operation: reads source from the patient graph, runs
    free text through the clinical redactor, then writes the cloned
    de-identified subgraph to the knowledge graph alongside SNOMED
    concepts (MERGE'd by snomed id with loud failure on missing).

    Raises HTTP 400 when the aspect is unknown, the source patient
    does not exist, or any referenced SNOMED concept is missing from
    the knowledge graph.
    """
    if body.aspect not in TEST_PATIENT_ASPECTS:
        raise HTTPException(
            status_code=400,
            detail=f"aspect must be one of {sorted(TEST_PATIENT_ASPECTS)}",
        )
    patient_graph = _patient_client()
    knowledge_graph = _client()
    try:
        return test_patient_clone.clone_patient_as_test_patient(
            patient_graph,
            knowledge_graph,
            source_patient_id=body.source_patient_id,
            aspect=body.aspect,
            created_by=getattr(scope, "user_email", "") or "unknown",
            description=body.description,
            redactor=get_default_redactor(),
        )
    except CloneError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        patient_graph.close()
        knowledge_graph.close()


@router.post("/test-patients/build")
def build_blank_patient(
    body: BuildBlankRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Create an empty :TestPatient for nlp / episodes / summarisation.

    The Build dialog uses this path for the three non-Guidelines
    aspects, where the form only collects a name + demographics and
    the per-aspect content is attached afterwards (free text +
    expected SNOMED codes for NLP, encounter timeline for Episodes,
    expected SBAR markdown for Summarisation).
    """
    client = _client()
    try:
        return test_patient_service.build_blank_patient_for_aspect(
            client,
            aspect=body.aspect,
            name=body.name,
            description=body.description,
            age=body.age,
            sex=body.sex,
            created_by=getattr(scope, "user_email", "") or "unknown",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        client.close()


class ScaffoldFromRuleRequest(BaseModel):
    """POST body for the AI scaffold-from-rule endpoint."""

    rule_id: str = Field(..., description="AppropriatenessRule id from the picker")
    aspect: Literal["nlp", "episodes", "summarisation"] = Field(
        default="summarisation",
        description="Which AI feature the test patient is for",
    )


@router.post("/test-patients/scaffold-from-rule")
def scaffold_from_rule(
    body: ScaffoldFromRuleRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Draft a test patient that should fire the picked rule.

    AI-assisted authoring, flow 1. The reviewer picks one rule from
    the tree picker; we ask Haiku to draft 1-2 plausible UK GP notes
    that mention every trigger SNOMED in the rule's criteria, plus a
    plausible age and sex inside any APPLIES_TO constraints. The
    expected SBAR is filled in deterministically from the rule (the
    LLM never drafts the test's own ground-truth answer).

    The new patient is persisted immediately and stamped with
    aiAssisted=true so the library can flag AI drafts for review.
    Failures (rule missing, LLM produced unusable JSON, demographic
    constraint broken, trigger missing from notes) raise
    :class:`ScaffoldError` and surface as HTTP 422 with a clear reason
    -- the reviewer can retry, fall back to Build a patient, or fix
    the rule.
    """
    client = _client()
    try:
        result = test_patient_scaffolder.scaffold_patient_from_rule_sync(
            client,
            rule_id=body.rule_id,
            aspect=body.aspect,
            created_by=getattr(scope, "user_email", "") or "unknown",
        )
    except ScaffoldError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - log + 5xx
        logger.exception("scaffold-from-rule failed")
        raise HTTPException(
            status_code=500, detail=f"Scaffold failed: {exc}"
        ) from exc
    finally:
        client.close()
    return {
        "patient_id": result.patient_id,
        "aspect": result.aspect,
        "rule_id": result.rule_id,
        "encounters_written": result.encounters_written,
        "expected_sbar_written": result.expected_sbar_written,
        "notes": result.notes,
    }


class ScaffoldFromScenarioRequest(BaseModel):
    """POST body for the AI scaffold-from-scenario endpoint."""

    scenario: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description=(
            "Free-text patient scenario, e.g. '67yo woman with 2-week "
            "visible haematuria, BP 140/85, PMHx HTN'."
        ),
    )
    aspect: Literal["nlp", "episodes", "summarisation"] = Field(
        default="summarisation",
        description="Which AI feature the test patient is for",
    )


@router.post("/test-patients/scaffold-from-scenario")
def scaffold_from_scenario(
    body: ScaffoldFromScenarioRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Draft a test patient that mirrors a free-text scenario.

    AI-assisted authoring, flow 2. The reviewer types a short
    scenario; we ask Haiku to expand it into demographics + UK GP
    notes + a list of clinical terms. Each term is resolved to
    SNOMED via the production terminology API, the rule engine is
    asked which AppropriatenessRules would fire on the resulting
    code list, and the expected SBAR (for the summarisation aspect)
    is filled in deterministically from the rule engine's verdict.

    The new patient is persisted immediately and stamped with
    aiAssisted=true and aiSourceKind='scenario' so the library can
    flag scenario drafts for review. The scenario text is preserved
    on the node so the row can show "from scenario: <text>" without
    a round-trip.

    Failures (scenario too short, LLM produced unusable JSON,
    terminology outage, no SNOMED concepts resolved, missing
    concepts in the knowledge graph) raise
    :class:`ScenarioScaffoldError` and surface as HTTP 422 with a
    clear reason -- the reviewer can retry, rephrase, or fall back
    to Build a patient.
    """
    client = _client()
    try:
        result = (
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync(
                client,
                scenario=body.scenario,
                aspect=body.aspect,
                created_by=getattr(scope, "user_email", "") or "unknown",
            )
        )
    except ScenarioScaffoldError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - log + 5xx
        logger.exception("scaffold-from-scenario failed")
        raise HTTPException(
            status_code=500, detail=f"Scaffold failed: {exc}"
        ) from exc
    finally:
        client.close()
    return {
        "patient_id": result.patient_id,
        "aspect": result.aspect,
        "scenario": result.scenario,
        "encounters_written": result.encounters_written,
        "expected_sbar_written": result.expected_sbar_written,
        "resolved_terms": [
            {
                "surface_form": row.surface_form,
                "lookup_term": row.lookup_term,
                "semantic_tag": row.semantic_tag,
                "assertion": row.assertion,
                "concept_id": row.concept_id,
                "preferred_term": row.preferred_term,
                "score": round(row.score, 4),
            }
            for row in result.resolved_terms
        ],
        "unresolved_terms": [
            {
                "surface_form": row.surface_form,
                "lookup_term": row.lookup_term,
                "semantic_tag": row.semantic_tag,
                "assertion": row.assertion,
                "score": round(row.score, 4),
            }
            for row in result.unresolved_terms
        ],
        "matched_rules": [
            {
                "rule_id": row.rule_id,
                "name": row.name,
                "recommendation_verbatim": row.recommendation_verbatim,
                "action_priority": row.action_priority,
                "guideline_title": row.guideline_title,
                "chapter_title": row.chapter_title,
            }
            for row in result.matched_rules
        ],
        "notes": result.notes,
    }


@router.get("/test-patients/guidelines")
def list_guidelines(scope: CallerScope = Depends(require_admin)) -> list[dict]:
    """Return guidelines that have at least one active rule (for the picker)."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_guidelines_for_picker(client)
    finally:
        client.close()


@router.get("/test-patients/rules")
def list_rules(
    guideline_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Case-insensitive substring filter"),
    limit: int = Query(default=200, ge=1, le=1000),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Return active / pending appropriateness rules for a picker.

    Powers the SBAR editor's "Matched rule IDs" lookup. The reviewer sees
    a plain-English label (the verbatim NICE recommendation), the chapter
    it lives in, the action priority and a few SNOMED triggers. The raw
    rule_id is kept in the payload because it is the saved value, but
    the UI never has to lead with it.
    """
    _ = scope
    client = _client()
    try:
        rows = test_patient_service.list_rules_for_picker(
            client, guideline_id=guideline_id
        )
    finally:
        client.close()

    needle = (q or "").strip().lower()
    slim: list[dict] = []
    for row in rows:
        triggers = [str(t) for t in (row.get("trigger_terms") or []) if t]
        display_label = _pick_display_label(row, triggers)
        item = {
            "rule_id": row.get("rule_id"),
            "status": row.get("status"),
            "name": row.get("name"),
            "display_label": display_label,
            "recommendation_text": row.get("recommendation_text"),
            "chapter_title": row.get("chapter_title"),
            "action_priority": row.get("action_priority"),
            "trigger_terms": triggers,
            "guideline_id": row.get("guideline_id"),
            "guideline_title": row.get("guideline_title"),
        }
        if needle:
            haystack = " ".join(
                str(item.get(key) or "")
                for key in (
                    "rule_id",
                    "name",
                    "display_label",
                    "recommendation_text",
                    "chapter_title",
                    "guideline_id",
                    "guideline_title",
                )
            )
            haystack += " " + " ".join(triggers)
            if needle not in haystack.lower():
                continue
        slim.append(item)
        if len(slim) >= limit:
            break
    return slim


def _pick_display_label(row: dict, triggers: list[str]) -> str:
    """Pick the most readable label we have for a rule.

    Order of preference:
      1. The verbatim NICE recommendation text (real sentence).
      2. The chapter title plus the first SNOMED trigger ("Section -- term").
      3. The chapter title alone.
      4. The (less helpful) rule.name.
      5. The raw rule id as a last resort.
    Truncated to keep the dropdown row visually tidy.
    """
    text = (row.get("recommendation_text") or "").strip()
    if text:
        return _truncate(text, 140)
    chapter = (row.get("chapter_title") or "").strip()
    if chapter and triggers:
        return _truncate(f"{chapter} -- {triggers[0]}", 140)
    if chapter:
        return _truncate(chapter, 140)
    name = (row.get("name") or "").strip()
    if name:
        return _truncate(name, 140)
    return str(row.get("rule_id") or "")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


@router.get("/test-patients/replay-reports")
def list_replay_reports(
    guideline_id: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_replay_reports(
            client,
            guideline_id=guideline_id,
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
        )
    finally:
        client.close()


@router.get("/test-patients/replay-reports/{report_id}")
def get_replay_report(
    report_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        report = test_patient_service.get_replay_report(client, report_id=report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Replay report not found")
        return report
    finally:
        client.close()


@router.get("/test-patients/{patient_id}/full")
def get_patient_full(
    patient_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Return the entire editable subgraph for one test patient.

    Used by the Knowledge > Test Patients > Edit drawer so the form
    can render encounters, codes and (for summarisation) the expected
    SBAR transcript without repeated round-trips.
    """
    _ = scope
    client = _client()
    try:
        row = test_patient_service.get_full_patient(
            client, patient_id=patient_id
        )
        if not row:
            raise HTTPException(
                status_code=404, detail="Test patient not found"
            )
        return row
    finally:
        client.close()


@router.patch("/test-patients/{patient_id}/full")
def update_patient_full(
    patient_id: str,
    body: EditorFullUpdateBody,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Replace the whole editable subgraph for one test patient.

    Atomic: validates SNOMED concepts first (loud failure when a
    referenced id is missing), updates the root profile, detaches
    every editor-managed child, then writes the new encounter list
    and (when aspect=summarisation) the expected SBAR. Returns 404
    when ``patient_id`` does not exist.

    Guidelines aspect is rejected here -- use ``PATCH /test-patients/{id}``
    so the rule-fire snapshot is preserved.
    """
    client = _client()
    try:
        result = test_patient_service.update_full_patient(
            client,
            patient_id=patient_id,
            aspect=body.aspect,
            name=body.name,
            description=body.description,
            age=body.age,
            sex=body.sex,
            encounters=[enc.model_dump() for enc in body.encounters],
            expected_sbar=(
                body.expected_sbar.model_dump()
                if body.expected_sbar is not None
                else None
            ),
            updated_by=getattr(scope, "user_email", "") or "unknown",
        )
        if not result.get("updated"):
            raise HTTPException(
                status_code=404, detail="Test patient not found"
            )
        return result
    except EditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        client.close()


@router.get("/test-patients/{patient_id}")
def get_patient(
    patient_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        row = test_patient_service.get_patient(client, patient_id=patient_id)
        if not row:
            raise HTTPException(status_code=404, detail="Test patient not found")
        return row
    finally:
        client.close()


@router.patch("/test-patients/{patient_id}")
def update_patient_route(
    patient_id: str,
    body: UpdateRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Replace a saved patient's profile + expectations in one call.

    Returns ``{id, updated, expectations_written}`` on success. Raises
    404 when ``patient_id`` does not exist (the Cypher MATCH returned
    zero rows so nothing was changed).
    """
    client = _client()
    try:
        result = test_patient_service.update_patient(
            client,
            patient_id=patient_id,
            payload=body.patient.to_payload(),
            expectations=[exp.model_dump() for exp in body.expectations],
            updated_by=getattr(scope, "user_email", "") or "unknown",
            ruleset_version=body.ruleset_version,
        )
        if not result.get("updated"):
            raise HTTPException(
                status_code=404, detail="Test patient not found"
            )
        return result
    finally:
        client.close()


@router.delete("/test-patients/{patient_id}")
def delete_patient(
    patient_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        deleted = test_patient_service.delete_patient(
            client, patient_id=patient_id
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Test patient not found")
        return {"deleted": deleted, "patient_id": patient_id}
    finally:
        client.close()


@router.post("/test-patients/generate")
def generate_patients(
    body: GenerateRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Synthesise happy/fail/boundary patients across the requested scope.

    Returns proposed patients (not yet persisted) for the reviewer to
    dry-run and confirm.  ``exclude_existing`` skips any whose
    content_hash already exists in that guideline.
    """
    _ = scope
    client = _client()
    try:
        return test_patient_generator.generate(
            client,
            scope_type=body.scope_type,
            guideline_id=body.guideline_id,
            rule_id=body.rule_id,
            branch_node_id=body.branch_node_id,
            depth=body.depth,
            exclude_existing=body.exclude_existing,
        )
    finally:
        client.close()


@router.post("/test-patients/replay")
def replay(
    body: ReplayRequest,
    scope: CallerScope = Depends(require_admin_or_service),
) -> dict:
    """Replay saved patients and diff against their snapshots.

    Accepts either an admin session cookie (admin UI) or a valid
    SERVICE_AUTH_SECRET Bearer token, so the post-compile hook in
    terminology-api (DI-LEO-AI-167) can replay test patients without a
    user session. Internal-network call only -- shared secret is the
    authentication boundary.
    """
    _ = scope
    client = _client()
    try:
        return test_patient_service.replay_scope(
            client,
            patient_ids=body.patient_ids,
            guideline_id=body.guideline_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
            persist_report=body.persist_report,
        )
    finally:
        client.close()


@router.post("/test-patients/sandbox-replay")
def sandbox_replay(
    body: SandboxReplayRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Compile DRAFT rules into a sandbox bitmap and replay saved patients.

    Returns the same per-patient diff shape as
    ``/test-patients/replay`` so the existing ReplayResultsDialog can
    render the result, plus a ``compile`` summary so the UI can show
    how many of the draft rules actually compiled.

    Safe by construction: the compile writes to ``scope_type='custom'``
    only, and the sandbox is dropped before the response returns. A
    Redis TTL on the sandbox keys catches missed cleanups.
    """
    _ = scope
    if not body.rules:
        raise HTTPException(
            status_code=400, detail="sandbox-replay requires at least one rule"
        )
    client = _client()
    try:
        return test_patient_service.sandbox_replay(
            client,
            body.rules,
            patient_ids=body.patient_ids,
            guideline_id=body.guideline_id,
            sandbox_id=body.sandbox_id,
            policy_mode=body.policy_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        client.close()
