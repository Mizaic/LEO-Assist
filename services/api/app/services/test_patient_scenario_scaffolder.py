"""AI-assisted scaffolder from a free-text scenario (flow 2).

Flow 2 of the AI-assisted authoring story for the Knowledge > Test
Patients tab. The reviewer types a short scenario like:

    "67yo woman with 2-week visible haematuria, BP 140/85, PMHx HTN"

and clicks "Author from a scenario". The scaffolder:

  1. Asks Haiku to expand the scenario into demographics + 1-2 short
     UK GP-style encounter notes + a list of clinical terms it
     pulled out of the prose.
  2. Resolves each clinical term to SNOMED via the production
     terminology API. The LLM never invents SNOMED ids; it only
     names a clean lookup_term per surface form.
  3. Calls the production rule engine (terminology API
     /guidelines/evaluate) with the resolved code list to find which
     AppropriatenessRules would fire.
  4. Persists a new :TestPatient with the encounters + per-encounter
     SNOMED codes + (for the summarisation aspect) an expected SBAR
     filled in from the rule engine's verdict.

Honesty discipline: the expected SBAR is built from the rule engine
output (the production source of truth), NOT from the LLM. The LLM
gets one job -- structuring the prose. The pipeline reasons about it
the same way it would about a real consultation.

Provenance: every patient saved this way is stamped with
``aiAssisted = true``, ``aiSourceKind = 'scenario'``, and the
scenario text is preserved on the node so the library can show "AI
draft from <scenario>" in the row for review.

All collaborators (LLM generator, terminology resolver, rule
evaluator) are INJECTABLE so unit tests drive the service without a
Bedrock connection or a running terminology API.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from app.db.neo4j_client import CodingGraphClient
from app.services import test_patient_service
from libs.prompts.test_patient_scenario_v1 import (
    SYSTEM_PROMPT,
    build_user_prompt,
    expected_field_set,
    normalise_terms,
)

logger = logging.getLogger(__name__)


_VALID_SEX = {"male", "female"}
_NON_GUIDELINE_ASPECTS = {"nlp", "episodes", "summarisation"}
_DEFAULT_ASPECT = "summarisation"
_MIN_SCENARIO_CHARS = 12
_MAX_SCENARIO_CHARS = 2000
_RESOLVE_SCORE_FLOOR = 0.45  # below this we treat the term as unresolved


class ScenarioScaffoldError(ValueError):
    """Raised when the AI draft is unusable.

    The router translates this into HTTP 422 -- the reviewer sees the
    reason and can either retry, fall back to "Build a patient", or
    rephrase the scenario.
    """


@dataclass(frozen=True)
class ResolvedTermRow:
    """One term after SNOMED resolution.

    `concept_id` is None when the term did not resolve above the
    score floor; the UI shows these as "needs review" so the
    reviewer can fix them by hand in the editor.
    """

    surface_form: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    concept_id: str | None
    preferred_term: str | None
    score: float


@dataclass(frozen=True)
class MatchedRuleRow:
    """One AppropriatenessRule that fired for the scenario."""

    rule_id: str
    name: str | None
    recommendation_verbatim: str | None
    action_priority: str | None
    guideline_title: str | None
    chapter_title: str | None


@dataclass
class ScenarioScaffoldResult:
    """What the router returns to the UI on success."""

    patient_id: str
    aspect: str
    scenario: str
    encounters_written: int
    expected_sbar_written: bool
    resolved_terms: list[ResolvedTermRow] = field(default_factory=list)
    unresolved_terms: list[ResolvedTermRow] = field(default_factory=list)
    matched_rules: list[MatchedRuleRow] = field(default_factory=list)
    notes: str = ""


# Type aliases for the injectable collaborators.
GeneratorFn = Callable[[str, str], Awaitable[dict[str, Any]]]
ResolverFn = Callable[[list[str]], dict[str, list[Any]]]
EvaluatorFn = Callable[[test_patient_service.PatientPayload], dict[str, Any]]


async def _default_generator(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Production generator -- routes to Bedrock via invoke_llm_json.

    Imported lazily so the unit tests do not drag in boto3.
    """
    from libs.llm_client.json_helper import invoke_llm_json

    return await invoke_llm_json(
        system_prompt=system_prompt,
        user_message=user_prompt,
        max_tokens=2000,
        temperature=0.2,
        agent_task="test_patient_scenario_v1",
        max_retries=2,
    )


def _default_resolver(terms: list[str]) -> dict[str, list[Any]]:
    """Production resolver -- routes to the terminology API."""
    from libs.terminology.client import TerminologyClient

    return TerminologyClient().resolve(terms)


def _default_evaluator(payload: test_patient_service.PatientPayload) -> dict:
    """Production evaluator -- routes to the rule engine."""
    return test_patient_service.evaluate_against_terminology(payload)


# ---------------------------------------------------------------------------
# Validation of the LLM response
# ---------------------------------------------------------------------------


def _validate_scenario(scenario: str) -> str:
    """Reject empty / silly scenarios before we burn a Haiku call."""
    cleaned = (scenario or "").strip()
    if len(cleaned) < _MIN_SCENARIO_CHARS:
        raise ScenarioScaffoldError(
            "Scenario is too short. Try at least a sentence -- e.g. "
            "'67yo woman with 2-week visible haematuria, BP 140/85'."
        )
    if len(cleaned) > _MAX_SCENARIO_CHARS:
        raise ScenarioScaffoldError(
            f"Scenario is too long ({len(cleaned)} characters). Trim it "
            f"under {_MAX_SCENARIO_CHARS} characters or split it into "
            "two scenarios."
        )
    return cleaned


def _validate_demographics(demographics: dict[str, Any]) -> dict[str, Any]:
    """Normalise + sanity-check the LLM-supplied demographics block."""
    if not isinstance(demographics, dict):
        raise ScenarioScaffoldError("AI response: 'demographics' must be an object.")
    age_raw = demographics.get("age")
    sex_raw = (demographics.get("sex") or "").strip().lower()
    try:
        age = int(age_raw) if age_raw is not None else None
    except (TypeError, ValueError):
        raise ScenarioScaffoldError(f"AI response: bad age value {age_raw!r}.")
    if age is None or not (0 < age < 130):
        raise ScenarioScaffoldError(
            f"AI response: age {age_raw!r} is outside 1-129."
        )
    if sex_raw not in _VALID_SEX:
        raise ScenarioScaffoldError(
            f"AI response: sex must be male/female, got {sex_raw!r}."
        )
    return {
        "age": age,
        "sex": sex_raw,
        "display_hint": (demographics.get("display_hint") or "").strip(),
    }


def _validate_encounters_shape(encounters: Any) -> list[dict[str, Any]]:
    """Light shape check before we resolve terms.

    We need at least one encounter with non-empty text. We do NOT
    require terms here because the resolver pass below is what
    decides whether the encounter is usable.
    """
    if not isinstance(encounters, list) or not encounters:
        raise ScenarioScaffoldError(
            "AI response: 'encounters' must be a non-empty list."
        )
    today = date.today()
    cleaned: list[dict[str, Any]] = []
    for index, raw in enumerate(encounters, start=1):
        if not isinstance(raw, dict):
            raise ScenarioScaffoldError(
                f"AI response: encounter #{index} must be an object."
            )
        text = (raw.get("text") or "").strip()
        if len(text) < 20:
            raise ScenarioScaffoldError(
                f"AI response: encounter #{index} text is too short."
            )
        offset = raw.get("date_offset_days")
        try:
            offset_int = int(offset) if offset is not None else 0
        except (TypeError, ValueError):
            offset_int = 0
        encounter_date = today + timedelta(days=min(offset_int, 0))
        cleaned.append(
            {
                "source_label": (
                    raw.get("source_label") or "GP consultation"
                ).strip(),
                "date": encounter_date.isoformat(),
                "text": text,
                "raw_terms": normalise_terms(raw.get("terms")),
            }
        )
    return cleaned


# ---------------------------------------------------------------------------
# SNOMED resolution
# ---------------------------------------------------------------------------


def _read_concept_id(candidate: Any) -> str | None:
    if isinstance(candidate, dict):
        cid = (
            candidate.get("concept_id")
            or candidate.get("conceptId")
            or candidate.get("snomed_concept_id")
        )
        return str(cid).strip() if cid else None
    cid = getattr(candidate, "concept_id", None)
    return str(cid).strip() if cid else None


def _read_preferred_term(candidate: Any) -> str | None:
    if isinstance(candidate, dict):
        term = (
            candidate.get("term")
            or candidate.get("preferredTerm")
            or candidate.get("preferred_term")
        )
        return str(term).strip() if term else None
    term = getattr(candidate, "term", None)
    return str(term).strip() if term else None


def _read_score(candidate: Any) -> float:
    if isinstance(candidate, dict):
        return float(candidate.get("score") or 0.0)
    return float(getattr(candidate, "score", 0.0) or 0.0)


def _resolve_terms(
    encounters: list[dict[str, Any]],
    resolver: ResolverFn,
) -> tuple[list[ResolvedTermRow], list[ResolvedTermRow]]:
    """Run the LLM-supplied lookup terms through the terminology API.

    Returns ``(resolved, unresolved)`` -- resolved entries carry a
    SNOMED concept id; unresolved entries kept their term text so
    the reviewer can fix them in the editor.
    """
    lookups: list[str] = []
    seen: set[str] = set()
    for enc in encounters:
        for term in enc.get("raw_terms") or []:
            key = term["lookup_term"].lower()
            if key in seen:
                continue
            seen.add(key)
            lookups.append(term["lookup_term"])

    if not lookups:
        return [], []

    try:
        results = resolver(lookups)
    except Exception as exc:  # noqa: BLE001 - resolver outage = loud failure
        raise ScenarioScaffoldError(
            "Could not reach the terminology service to resolve "
            f"clinical terms ({exc}). Try again or use Build a patient."
        ) from exc

    resolved: list[ResolvedTermRow] = []
    unresolved: list[ResolvedTermRow] = []
    seen_resolved: set[tuple[str, str]] = set()
    for enc in encounters:
        for term in enc.get("raw_terms") or []:
            candidates = results.get(term["lookup_term"]) or []
            top = candidates[0] if candidates else None
            cid = _read_concept_id(top) if top else None
            score = _read_score(top) if top else 0.0
            row = ResolvedTermRow(
                surface_form=term["surface_form"],
                lookup_term=term["lookup_term"],
                semantic_tag=term["semantic_tag"],
                assertion=term["assertion"],
                concept_id=cid if cid and score >= _RESOLVE_SCORE_FLOOR else None,
                preferred_term=_read_preferred_term(top) if top else None,
                score=score,
            )
            if row.concept_id:
                key = (row.concept_id, row.assertion)
                if key in seen_resolved:
                    continue
                seen_resolved.add(key)
                resolved.append(row)
            else:
                unresolved.append(row)
    return resolved, unresolved


def _attach_codes_to_encounters(
    encounters: list[dict[str, Any]],
    resolved_lookup: dict[str, ResolvedTermRow],
) -> list[dict[str, Any]]:
    """Build the encounter list in the shape `update_full_patient` wants.

    Per-encounter codes use the resolved SNOMED concept ids; we
    de-dupe within an encounter so the editor never shows the same
    (concept, assertion) twice.
    """
    out: list[dict[str, Any]] = []
    for enc in encounters:
        seen: set[tuple[str, str]] = set()
        codes: list[dict[str, Any]] = []
        for raw in enc.get("raw_terms") or []:
            lookup_key = raw["lookup_term"].lower()
            row = resolved_lookup.get(lookup_key)
            if row is None or not row.concept_id:
                continue
            key = (row.concept_id, row.assertion)
            if key in seen:
                continue
            seen.add(key)
            codes.append(
                {
                    "concept_id": row.concept_id,
                    "term": row.preferred_term or raw["surface_form"],
                    "assertion": row.assertion,
                }
            )
        out.append(
            {
                "source_label": enc["source_label"],
                "date": enc["date"],
                "text": enc["text"],
                "codes": codes,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Rule evaluation + expected SBAR (deterministic, never asks the LLM)
# ---------------------------------------------------------------------------


_PRIORITY_ORDER = {"2ww": 0, "two_week_wait": 0, "urgent": 1, "routine": 2}


def _priority_rank(priority: str | None) -> int:
    return _PRIORITY_ORDER.get((priority or "").lower(), 9)


def _parse_matched_rules(eval_result: dict[str, Any]) -> list[MatchedRuleRow]:
    rows: list[MatchedRuleRow] = []
    for entry in eval_result.get("matched_rules") or []:
        if not isinstance(entry, dict):
            continue
        rid = (entry.get("rule_id") or "").strip()
        if not rid:
            continue
        rows.append(
            MatchedRuleRow(
                rule_id=rid,
                name=(entry.get("name") or "").strip() or None,
                recommendation_verbatim=(
                    entry.get("recommendation_verbatim") or ""
                ).strip()
                or None,
                action_priority=(
                    entry.get("action") or entry.get("action_priority") or ""
                ).strip()
                or None,
                guideline_title=(entry.get("guideline_title") or "").strip()
                or None,
                chapter_title=(entry.get("chapter_title") or "").strip() or None,
            )
        )
    rows.sort(key=lambda r: (_priority_rank(r.action_priority), r.rule_id))
    return rows


def _expected_sbar_from_rules(
    matched: list[MatchedRuleRow],
    *,
    scenario: str,
    reviewer_focus: str,
) -> dict[str, Any]:
    """Build the ground-truth SBAR from the rule engine, not the LLM.

    When no rule fires, we still seed an SBAR so the reviewer has a
    skeleton to edit (matched_rule_ids is empty -- the test will
    expect "no rule should fire"). When at least one rule fires, the
    top-priority rule's verbatim recommendation becomes the
    Recommendation, and the action priority becomes the expected
    action.
    """
    matched_ids = [r.rule_id for r in matched]
    focus = reviewer_focus.strip() or (
        f"Confirm the AI handles this scenario: {scenario[:120]}".rstrip()
    )
    if not matched:
        return {
            "situation_md": "",
            "background_md": "",
            "recommendation_md": (
                "No rule fires for this scenario -- the AI should not "
                "raise a referral. Edit if a different outcome is "
                "expected."
            ),
            "matched_rule_ids": [],
            "required_phrases": [],
            "banned_phrases": [],
            "expected_action_priority": None,
            "reviewer_focus": focus,
            "evaluator_outage": False,
        }
    top = matched[0]
    return {
        "situation_md": "",
        "background_md": "",
        "recommendation_md": top.recommendation_verbatim
        or f"(rule {top.rule_id} has no recommendation text on file)",
        "matched_rule_ids": matched_ids,
        "required_phrases": [],
        "banned_phrases": [],
        "expected_action_priority": top.action_priority,
        "reviewer_focus": focus,
        "evaluator_outage": False,
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


# LONG FUNCTION: top-level orchestrator wires 5 sequential phases
# (validate -> draft -> resolve -> evaluate -> persist). Splitting
# would scatter the patient_id, draft, and result state across
# helpers and make the failure paths harder to follow.
async def scaffold_patient_from_scenario(
    client: CodingGraphClient,
    *,
    scenario: str,
    aspect: str = _DEFAULT_ASPECT,
    created_by: str = "",
    generator: GeneratorFn | None = None,
    resolver: ResolverFn | None = None,
    evaluator: EvaluatorFn | None = None,
) -> ScenarioScaffoldResult:
    """Draft + persist a test patient that mirrors `scenario`.

    Raises :class:`ScenarioScaffoldError` for any user-recoverable
    failure (scenario too short, LLM produced a bad draft, terminology
    outage, missing concepts in the knowledge graph). The router
    maps this to HTTP 422.
    """
    aspect_lc = (aspect or _DEFAULT_ASPECT).strip().lower()
    if aspect_lc not in _NON_GUIDELINE_ASPECTS:
        raise ScenarioScaffoldError(
            f"Aspect {aspect!r} is not supported by the scaffolder. "
            f"Choose one of {sorted(_NON_GUIDELINE_ASPECTS)}."
        )

    cleaned_scenario = _validate_scenario(scenario)
    user_prompt = build_user_prompt(scenario=cleaned_scenario)

    gen = generator or _default_generator
    draft = await gen(SYSTEM_PROMPT, user_prompt)
    if not isinstance(draft, dict) or "error" in draft:
        raise ScenarioScaffoldError(
            "AI scaffolder did not return JSON: "
            f"{draft.get('error') if isinstance(draft, dict) else draft!r}"
        )
    missing_keys = expected_field_set() - set(draft)
    if missing_keys:
        raise ScenarioScaffoldError(
            f"AI response missing required keys: {sorted(missing_keys)}."
        )

    demographics = _validate_demographics(draft.get("demographics") or {})
    encounters_raw = _validate_encounters_shape(draft.get("encounters"))
    reviewer_focus = (draft.get("reviewer_focus") or "").strip()

    resolve = resolver or _default_resolver
    resolved, unresolved = _resolve_terms(encounters_raw, resolve)

    if not resolved and not unresolved:
        raise ScenarioScaffoldError(
            "AI did not pick out any clinical terms from the scenario. "
            "Add a symptom, sign or diagnosis (e.g. 'haematuria') and "
            "retry."
        )

    resolved_lookup: dict[str, ResolvedTermRow] = {
        row.lookup_term.lower(): row for row in resolved
    }
    encounters = _attach_codes_to_encounters(encounters_raw, resolved_lookup)

    matched_rules: list[MatchedRuleRow] = []
    eval_payload = test_patient_service.PatientPayload(
        codes=[row.concept_id or "" for row in resolved if row.concept_id],
        age=float(demographics["age"]),
        sex=demographics["sex"],
    )
    if eval_payload.normalised_codes() and aspect_lc == "summarisation":
        evaluate = evaluator or _default_evaluator
        try:
            eval_result = evaluate(eval_payload)
        except Exception as exc:  # noqa: BLE001 - rule outage = loud failure
            raise ScenarioScaffoldError(
                "Could not reach the rule engine to predict matched "
                f"rules ({exc}). Try again or use Build a patient."
            ) from exc
        matched_rules = _parse_matched_rules(eval_result or {})

    expected_sbar: dict | None = None
    if aspect_lc == "summarisation":
        expected_sbar = _expected_sbar_from_rules(
            matched_rules,
            scenario=cleaned_scenario,
            reviewer_focus=reviewer_focus,
        )

    display_hint = demographics["display_hint"]
    name = display_hint or "AI scenario draft"
    description = f"AI-scaffolded test patient from scenario: {cleaned_scenario[:140]}"

    blank = test_patient_service.build_blank_patient_for_aspect(
        client,
        aspect=aspect_lc,
        name=name,
        description=description,
        age=float(demographics["age"]),
        sex=demographics["sex"],
        created_by=created_by,
    )
    patient_id = blank["id"]

    # Stamp the AI provenance properties so the library can flag
    # scenario drafts and later show a "review AI drafts" badge. The
    # scenario text is preserved on the node so the row in the table
    # can show "from scenario: <text>" without an extra round-trip.
    client.run(
        """
        MATCH (tp:TestPatient {id: $id, is_test: true})
        SET tp.aiAssisted    = true,
            tp.aiSourceKind  = 'scenario',
            tp.aiSourceText  = $scenario,
            tp.aiPromptVersion = 'test_patient_scenario_v1',
            tp.generation_source = 'ai_scaffold_from_scenario',
            tp.updated_at    = datetime()
        """,
        id=patient_id,
        scenario=cleaned_scenario,
    )

    update = test_patient_service.update_full_patient(
        client,
        patient_id=patient_id,
        aspect=aspect_lc,
        name=name,
        description=description,
        age=float(demographics["age"]),
        sex=demographics["sex"],
        encounters=encounters,
        expected_sbar=expected_sbar,
        updated_by=created_by,
    )

    notes_bits: list[str] = []
    notes_bits.append(
        f"Scaffolded a {aspect_lc} test patient from a "
        f"{len(cleaned_scenario)}-char scenario with "
        f"{len(encounters)} encounter(s)."
    )
    notes_bits.append(
        f"{len(resolved)} term(s) resolved to SNOMED, "
        f"{len(unresolved)} need review."
    )
    if aspect_lc == "summarisation":
        if matched_rules:
            top = matched_rules[0]
            notes_bits.append(
                f"Top matched rule: {top.rule_id} "
                f"({top.action_priority or 'no priority'}). "
                f"{len(matched_rules)} rule(s) fired in total."
            )
        elif resolved:
            notes_bits.append(
                "No rules fired -- expected SBAR seeded with a "
                "'no referral' skeleton for the reviewer to edit."
            )
        else:
            notes_bits.append(
                "No SNOMED codes resolved -- expected SBAR was not "
                "evaluated. Fix the unresolved terms then re-run."
            )
    notes_bits.append("Open the editor to review and edit before saving.")

    return ScenarioScaffoldResult(
        patient_id=patient_id,
        aspect=aspect_lc,
        scenario=cleaned_scenario,
        encounters_written=int(update.get("encounters_written") or 0),
        expected_sbar_written=bool(update.get("expected_sbar_written")),
        resolved_terms=resolved,
        unresolved_terms=unresolved,
        matched_rules=matched_rules,
        notes=" ".join(notes_bits),
    )


def scaffold_patient_from_scenario_sync(
    client: CodingGraphClient,
    *,
    scenario: str,
    aspect: str = _DEFAULT_ASPECT,
    created_by: str = "",
    generator: GeneratorFn | None = None,
    resolver: ResolverFn | None = None,
    evaluator: EvaluatorFn | None = None,
) -> ScenarioScaffoldResult:
    """Synchronous entrypoint for FastAPI handlers.

    FastAPI's sync routes cannot await directly; we run the coroutine
    in a fresh event loop so the rest of this module can stay async.
    """
    return asyncio.run(
        scaffold_patient_from_scenario(
            client,
            scenario=scenario,
            aspect=aspect,
            created_by=created_by,
            generator=generator,
            resolver=resolver,
            evaluator=evaluator,
        )
    )
