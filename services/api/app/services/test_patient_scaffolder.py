"""AI-assisted scaffolder for the Knowledge > Test Patients tab.

Flow 1 of the AI-assisted authoring story: the reviewer picks one
AppropriatenessRule, we ask Haiku to draft a synthetic patient that
should make that rule fire, and the result lands in the editor for
the reviewer to tweak and save.

Design notes:
  - The expected SBAR is filled in DETERMINISTICALLY (we copy the
    rule's verbatim recommendation into the Recommendation section and
    the action priority into expected_action_priority). The LLM never
    drafts the test's own ground-truth answer; that is a hard rule
    because otherwise the test would be checking the LLM against
    itself.
  - SNOMED concept ids come straight from the rule logic tree (saved
    graph row, or the unsaved editor draft when supplied). The LLM
    never invents SNOMED ids; it only paraphrases the preferred terms
    into encounter prose.
  - Every saved patient is stamped with `aiAssisted: true`,
    `aiSourceKind: 'rule'`, and `aiSourceId: <rule_id>` so we can
    distinguish AI-scaffolded patients from manual / clone / SBAR-seed
    in the library and later add a "review AI drafts" queue.
  - The LLM call is INJECTABLE (`generator` parameter) so unit tests
    drive the service without a Bedrock connection. The default
    generator goes through `libs.llm_client.json_helper.invoke_llm_json`.

Failure mode: if Haiku returns malformed JSON, fails to mention every
trigger SNOMED, or breaks a demographic constraint we raise
:class:`ScaffoldError` and write NOTHING. The router translates that
into a 4xx so the reviewer sees the failure rather than a half-baked
patient.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from app.db.neo4j_client import CodingGraphClient
from app.services import test_patient_service
from app.services._logic_tree import (
    extract_concept_triggers,
    extract_demographic_constraints,
    extract_satisfying_pathways,
    extract_satisfying_concept_sets,
    extract_satisfying_concepts,
    parse_logic_json,
)
from libs.cypher.test_patient_queries import READ_RULE_FOR_SCAFFOLD
from libs.prompts.test_patient_scaffold_v1 import (
    SYSTEM_PROMPT,
    build_user_prompt,
    expected_field_set,
)

logger = logging.getLogger(__name__)


_VALID_SEX = {"male", "female"}
_NON_GUIDELINE_ASPECTS = {"nlp", "episodes", "summarisation"}
_DEFAULT_ASPECT_FOR_RULE = "summarisation"


class ScaffoldError(ValueError):
    """Raised when the AI draft is unusable.

    The router translates this into HTTP 422 -- the reviewer sees the
    reason and can either retry, fall back to Build a patient, or fix
    the rule.
    """


@dataclass(frozen=True)
class ScaffoldResult:
    """What the router returns to the UI on success."""

    patient_id: str
    patient_ids: list[str]
    aspect: str
    rule_id: str
    encounters_written: int
    expected_sbar_written: bool
    notes: str


# Type alias for the injectable LLM call. Async so the production
# implementation can stream from Bedrock without blocking the worker.
GeneratorFn = Callable[[str, str], Awaitable[dict[str, Any]]]


async def _default_generator(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Production generator -- routes to Bedrock via invoke_llm_json.

    Imported lazily so the unit tests don't drag in boto3 / Bedrock.
    """
    from libs.llm_client.json_helper import invoke_llm_json

    return await invoke_llm_json(
        system_prompt=system_prompt,
        user_message=user_prompt,
        max_tokens=1500,
        temperature=0.2,
        agent_task="test_patient_scaffold_v1",
        max_retries=2,
    )


# ---------------------------------------------------------------------------
# Rule reader
# ---------------------------------------------------------------------------


def load_rule_for_scaffold(
    client: CodingGraphClient,
    *,
    rule_id: str,
    draft_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pull every field the scaffolder needs about one rule.

    The cypher returns ``logic_json`` (a raw JSON blob) and we walk it
    here to derive the trigger SNOMED concepts and any demographic
    constraints. The walker is shared with the picker so the two
    surfaces always agree.

    Backwards compatibility: if a caller (typically a unit test) hands
    us a row that already has populated ``triggers`` /
    ``demographic_constraints`` and no ``logic_json``, we use those as
    the source of truth. Production rows always carry ``logic_json``.

    Raises :class:`ScaffoldError` if the rule does not exist or has no
    concept criteria the scaffolder can target -- the router then
    returns a 422 with a plain-English reason.
    """
    rows = client.run(READ_RULE_FOR_SCAFFOLD, rule_id=rule_id)
    if not rows:
        raise ScaffoldError(
            f"Rule {rule_id!r} was not found. Pick a rule from the tree "
            "picker -- only active or pending rules can be scaffolded."
        )
    row = dict(rows[0])
    if draft_rule:
        _apply_draft_rule(row, draft_rule)
    tree = parse_logic_json(row.get("logic_json"))
    if tree is not None:
        all_triggers = extract_concept_triggers(tree)
        must_mention = extract_satisfying_concepts(tree)
        row["all_triggers"] = all_triggers
        # ``triggers`` is the briefing list that downstream consumers
        # (prompt formatter, code-attacher, validator) all read. We
        # narrow it to the smallest satisfying subset so the LLM is
        # only asked to write up the concepts that actually need to
        # appear for the rule to fire. Falling back to the full union
        # keeps malformed / unrecognised trees from breaking the flow.
        row["triggers"] = must_mention or all_triggers
        row["pathways"] = extract_satisfying_pathways(tree)
        row["pathway_trigger_sets"] = extract_satisfying_concept_sets(tree)
        row["demographic_constraints"] = extract_demographic_constraints(tree)
    else:
        legacy = list(row.get("triggers") or [])
        row["triggers"] = legacy
        row["all_triggers"] = legacy
        row["pathways"] = (
            [
                {
                    "triggers": legacy,
                    "demographic_constraints": list(
                        row.get("demographic_constraints") or []
                    ),
                }
            ]
            if legacy
            else []
        )
        row["pathway_trigger_sets"] = [legacy] if legacy else []
        row["demographic_constraints"] = list(row.get("demographic_constraints") or [])
    if not row["triggers"]:
        raise ScaffoldError(
            f"Rule {rule_id!r} has no SNOMED criteria attached. The "
            "scaffolder cannot draft notes without at least one trigger "
            "concept -- fix the rule before scaffolding."
        )
    return row


def _apply_draft_rule(row: dict[str, Any], draft_rule: dict[str, Any]) -> None:
    """Overlay unsaved editor fields before deriving scaffold triggers."""
    row["logic_json"] = (
        draft_rule.get("logic_tree")
        or draft_rule.get("logicJson")
        or row.get("logic_json")
    )
    row["rule_name"] = (
        draft_rule.get("name") or draft_rule.get("rule_name") or row.get("rule_name")
    )
    row["recommendation_text"] = (
        draft_rule.get("recommendation_text")
        or draft_rule.get("recommendation_verbatim")
        or row.get("recommendation_text")
    )
    row["chapter_title"] = draft_rule.get("chapter_title") or row.get("chapter_title")
    row["guideline_title"] = draft_rule.get("guideline_title") or row.get(
        "guideline_title"
    )
    row["guideline_id"] = draft_rule.get("guideline_id") or row.get("guideline_id")
    row["action_priority"] = (
        draft_rule.get("action_priority")
        or draft_rule.get("strength")
        or row.get("action_priority")
    )


# ---------------------------------------------------------------------------
# Validation of the LLM response
# ---------------------------------------------------------------------------


def _validate_demographics(
    demographics: dict[str, Any],
    constraints: list[dict],
) -> dict[str, Any]:
    """Normalise + sanity-check the LLM-supplied demographics block."""
    if not isinstance(demographics, dict):
        raise ScaffoldError("AI response: 'demographics' must be an object.")
    age_raw = demographics.get("age")
    sex_raw = (demographics.get("sex") or "").strip().lower()
    try:
        age = int(age_raw) if age_raw is not None else None
    except (TypeError, ValueError):
        raise ScaffoldError(f"AI response: bad age value {age_raw!r}.")
    if age is None or not (0 < age < 130):
        raise ScaffoldError(f"AI response: age {age_raw!r} is outside 1-129.")
    if sex_raw not in _VALID_SEX:
        raise ScaffoldError(f"AI response: sex must be male/female, got {sex_raw!r}.")
    for c in constraints or []:
        field = (c.get("field") or "").strip().lower()
        op = (c.get("operator") or "").strip()
        value = c.get("value")
        if field == "age" and value is not None:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if op in {">=", "ge"} and age < v:
                raise ScaffoldError(
                    f"AI response: age {age} breaks APPLIES_TO age >= {v}."
                )
            if op in {">", "gt"} and age <= v:
                raise ScaffoldError(
                    f"AI response: age {age} breaks APPLIES_TO age > {v}."
                )
            if op in {"<=", "le"} and age > v:
                raise ScaffoldError(
                    f"AI response: age {age} breaks APPLIES_TO age <= {v}."
                )
            if op in {"<", "lt"} and age >= v:
                raise ScaffoldError(
                    f"AI response: age {age} breaks APPLIES_TO age < {v}."
                )
        if field == "sex" and value:
            v = str(value).strip().lower()
            if v in _VALID_SEX and v != sex_raw:
                raise ScaffoldError(
                    f"AI response: sex {sex_raw!r} breaks APPLIES_TO sex={v!r}."
                )
    return {
        "age": age,
        "sex": sex_raw,
        "display_hint": (demographics.get("display_hint") or "").strip(),
    }


def _validate_encounters(
    encounters: Any,
    triggers: list[dict],
) -> list[dict[str, Any]]:
    """Normalise + sanity-check the LLM-supplied encounter list."""
    if not isinstance(encounters, list) or not encounters:
        raise ScaffoldError("AI response: 'encounters' must be a non-empty list.")
    today = date.today()
    cleaned: list[dict[str, Any]] = []
    for index, raw in enumerate(encounters, start=1):
        if not isinstance(raw, dict):
            raise ScaffoldError(f"AI response: encounter #{index} must be an object.")
        text = (raw.get("text") or "").strip()
        if len(text) < 20:
            raise ScaffoldError(f"AI response: encounter #{index} text is too short.")
        offset = raw.get("date_offset_days")
        try:
            offset_int = int(offset) if offset is not None else 0
        except (TypeError, ValueError):
            offset_int = 0
        encounter_date = today + timedelta(days=min(offset_int, 0))
        cleaned.append(
            {
                "source_label": (raw.get("source_label") or "GP consultation").strip(),
                "date": encounter_date.isoformat(),
                "text": text,
                "codes": _codes_for_encounter(text, triggers),
            }
        )
    _assert_triggers_in_text(cleaned, triggers)
    if not any(encounter["codes"] for encounter in cleaned):
        cleaned[0]["codes"] = _codes_from_triggers(triggers)
    return cleaned


def _assert_triggers_in_text(
    encounters: list[dict],
    triggers: list[dict],
) -> None:
    """Every trigger preferred-term must appear in at least one note.

    The check is deliberately loose: we lower-case everything and look
    for the preferred term as a substring. The LLM is told to use the
    exact preferred term wherever possible, but a near-synonym ("blood
    in the urine" for "haematuria") will pass too as long as it is in
    SOME encounter -- the production NER pipeline is what actually has
    to recover the SNOMED, this check just guards against a draft that
    forgot to mention the symptom altogether.
    """
    blob = _normalise_trigger_text(" ".join((e.get("text") or "") for e in encounters))
    missing: list[str] = []
    for t in triggers:
        if _trigger_mentioned(blob, t):
            continue
        missing.append(t.get("preferred_term") or t.get("concept_id") or "?")
    if missing:
        raise ScaffoldError(
            "AI response: encounter notes did not mention every trigger "
            f"({', '.join(missing)}). Retry the scaffold or edit the "
            "draft by hand."
        )


def _codes_for_encounter(text: str, triggers: list[dict]) -> list[dict[str, Any]]:
    blob = _normalise_trigger_text(text)
    return [
        code
        for trigger in triggers
        if _trigger_mentioned(blob, trigger)
        for code in [_code_from_trigger(trigger)]
        if code is not None
    ]


def _codes_from_triggers(triggers: list[dict]) -> list[dict[str, Any]]:
    return [
        code
        for trigger in triggers
        for code in [_code_from_trigger(trigger)]
        if code is not None
    ]


def _code_from_trigger(trigger: dict) -> dict[str, Any] | None:
    concept_id = (trigger or {}).get("concept_id")
    if not concept_id:
        return None
    return {
        "concept_id": str(concept_id).strip(),
        "term": (trigger.get("preferred_term") or "").strip() or None,
        "assertion": "present",
    }


_UK_US_SPELLING_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("-", " "),
    # UK GP notes often use British spelling; SNOMED preferred terms are US.
    ("diarrhoea", "diarrhea"),
    ("diarrhoeic", "diarrheic"),
    ("anaemia", "anemia"),
    ("anaemic", "anemic"),
    ("oedema", "edema"),
    ("oesophagus", "esophagus"),
    ("oesophageal", "esophageal"),
    ("leukaemia", "leukemia"),
    ("leukaemic", "leukemic"),
    ("tumour", "tumor"),
    ("tumours", "tumors"),
    ("faeces", "feces"),
    ("faecal", "fecal"),
    ("coeliac", "celiac"),
    ("haem", "hem"),
    ("dyspnoea", "dyspnea"),
    ("dyspnoeic", "dyspneic"),
)

# GP notes rarely use the exact SNOMED preferred term. Accept phrases the
# terminology layer already maps to the same concept in production.
_TRIGGER_MENTION_SYNONYMS_BY_CONCEPT: dict[str, tuple[str, ...]] = {
    "262285001": (
        "weight loss",
        "losing weight",
        "lost weight",
        "weight reduced",
        "unintentional weight loss",
    ),
    "267036007": (
        "breathlessness",
        "shortness of breath",
        "short of breath",
        "breathless",
    ),
}

_TRIGGER_MENTION_SYNONYMS_BY_HEAD: dict[str, tuple[str, ...]] = {
    "weight decreased": _TRIGGER_MENTION_SYNONYMS_BY_CONCEPT["262285001"],
    "dyspnea": _TRIGGER_MENTION_SYNONYMS_BY_CONCEPT["267036007"],
}

_TRIGGER_MENTION_REGEX_BY_CONCEPT: dict[str, tuple[str, ...]] = {
    "262285001": (
        r"\blost (?:approximately |about |approx\.? )?\d",
        r"\bweight (?:is )?down\b",
    ),
    "267036007": (
        r"\bsob\b",
        r"\bcan(?:'|no)?t breathe\b",
    ),
}


def _trigger_mention_phrases(trigger: dict) -> list[str]:
    term = _normalise_trigger_text(trigger.get("preferred_term") or "")
    head = term.split("(", 1)[0].strip()
    phrases: list[str] = []
    if head:
        phrases.append(head)
    concept_id = str((trigger or {}).get("concept_id") or "").strip()
    phrases.extend(_TRIGGER_MENTION_SYNONYMS_BY_CONCEPT.get(concept_id, ()))
    phrases.extend(_TRIGGER_MENTION_SYNONYMS_BY_HEAD.get(head, ()))
    seen: set[str] = set()
    out: list[str] = []
    for phrase in phrases:
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        out.append(phrase)
    return out


def _trigger_mentioned(normalised_text: str, trigger: dict) -> bool:
    for phrase in _trigger_mention_phrases(trigger):
        if phrase in normalised_text:
            return True
    concept_id = str((trigger or {}).get("concept_id") or "").strip()
    for pattern in _TRIGGER_MENTION_REGEX_BY_CONCEPT.get(concept_id, ()):
        if re.search(pattern, normalised_text):
            return True
    return False


def _normalise_trigger_text(value: str) -> str:
    text = value.strip().lower()
    for old, new in _UK_US_SPELLING_REPLACEMENTS:
        text = text.replace(old, new)
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Expected SBAR (deterministic -- never asks the LLM)
# ---------------------------------------------------------------------------


def _friendly_rule_label(rule: dict[str, Any]) -> str:
    """Pick the most human-readable label we have for ``rule``.

    Reviewers should NEVER see the raw rule_id (for example
    ``rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3`` -- see
    .cursor/rules/health-literacy.mdc). We fall through three options
    in order of friendliness, and only land on the rule_id when
    nothing better exists in the rule payload.

    1. ``rule_name`` -- a curated short title if the editor set one.
    2. ``recommendation_text`` -- the verbatim NICE recommendation,
       trimmed to ~120 chars and stripped of trailing colons so the
       label reads as a noun phrase, not a half-finished sentence.
    3. ``rule_id`` -- last resort.

    The friendly label is wrapped in straight quotes so callers can
    drop it into "for X" sentences without ambiguity about where the
    label ends.
    """

    name = (rule.get("rule_name") or "").strip()
    if name:
        return f'"{name}"'

    rec = (rule.get("recommendation_text") or "").strip()
    if rec:
        snippet = rec.split("\n", 1)[0].strip().rstrip(":").rstrip(".")
        if len(snippet) > 120:
            snippet = snippet[:117].rstrip() + "..."
        return f'"{snippet}"'

    return rule["rule_id"]


def _expected_sbar_from_rule(rule: dict[str, Any], reviewer_focus: str) -> dict:
    """Build the ground-truth SBAR straight from the rule, not the LLM.

    The test exists to check the AI; it MUST NOT use the AI's own words
    as the ground truth. Situation / Background are left for the
    reviewer to flesh out (they depend on the encounter text the LLM
    drafted), but Recommendation, action priority and matched rule are
    set deterministically from the rule.
    """
    rec = (rule.get("recommendation_text") or "").strip()
    chapter = (rule.get("chapter_title") or "").strip()
    guideline = (rule.get("guideline_title") or "").strip()
    return {
        "situation_md": "",
        "background_md": "",
        "recommendation_md": rec or "(rule has no recommendation text on file)",
        "matched_rule_ids": [rule["rule_id"]],
        "required_phrases": [],
        "banned_phrases": [],
        "expected_action_priority": (rule.get("action_priority") or "").strip() or None,
        "reviewer_focus": (
            reviewer_focus.strip()
            or f"Confirm the {guideline or 'rule'} fires for this scenario."
        ),
        "evaluator_outage": False,
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


async def scaffold_patient_from_rule(
    client: CodingGraphClient,
    *,
    rule_id: str,
    aspect: str = _DEFAULT_ASPECT_FOR_RULE,
    created_by: str = "",
    generator: GeneratorFn | None = None,
    draft_rule: dict[str, Any] | None = None,
) -> ScaffoldResult:
    """Draft + persist a test patient that should fire `rule_id`.

    Raises :class:`ScaffoldError` for any user-recoverable failure
    (rule not found, LLM produced a bad draft, concept missing from
    the knowledge graph, ...). The router maps this to HTTP 422.
    """
    aspect_lc = (aspect or _DEFAULT_ASPECT_FOR_RULE).strip().lower()
    if aspect_lc not in _NON_GUIDELINE_ASPECTS:
        raise ScaffoldError(
            f"Aspect {aspect!r} is not supported by the scaffolder. "
            f"Choose one of {sorted(_NON_GUIDELINE_ASPECTS)}."
        )

    rule = load_rule_for_scaffold(client, rule_id=rule_id, draft_rule=draft_rule)
    gen = generator or _default_generator
    pathways = rule.get("pathways") or [
        {
            "triggers": rule.get("triggers") or [],
            "demographic_constraints": rule.get("demographic_constraints") or [],
        }
    ]
    pathways = [p for p in pathways if p.get("triggers")] or pathways
    results: list[ScaffoldResult] = []
    total = len(pathways)
    try:
        for index, pathway in enumerate(pathways, start=1):
            results.append(
                await _scaffold_one_patient(
                    client,
                    rule=rule,
                    triggers=pathway.get("triggers") or [],
                    demographic_constraints=_pathway_demographics(pathway, rule),
                    aspect_lc=aspect_lc,
                    created_by=created_by,
                    generator=gen,
                    pathway_index=index,
                    pathway_total=total,
                )
            )
    except Exception:
        _delete_partial_scaffolds(client, [r.patient_id for r in results])
        raise
    patient_ids = [r.patient_id for r in results]
    first = results[0]
    return ScaffoldResult(
        patient_id=first.patient_id,
        patient_ids=patient_ids,
        aspect=first.aspect,
        rule_id=first.rule_id,
        encounters_written=sum(r.encounters_written for r in results),
        expected_sbar_written=any(r.expected_sbar_written for r in results),
        notes=(
            f"Scaffolded {len(results)} {aspect_lc} test patient"
            f"{'' if len(results) == 1 else 's'} against {rule['rule_id']}. "
            "Each top-level pathway gets its own saved patient."
        ),
    )


def _pathway_demographics(pathway: dict, rule: dict[str, Any]) -> list[dict]:
    if "demographic_constraints" in pathway:
        return list(pathway.get("demographic_constraints") or [])
    return list(rule.get("demographic_constraints") or [])


def _delete_partial_scaffolds(
    client: CodingGraphClient, patient_ids: list[str]
) -> None:
    """Best-effort rollback when a later pathway fails validation."""
    for patient_id in patient_ids:
        try:
            test_patient_service.delete_patient(client, patient_id=patient_id)
        except Exception:  # noqa: BLE001 - rollback must not hide root cause
            logger.warning("Failed to delete partial scaffold %s", patient_id)


async def _scaffold_one_patient(
    client: CodingGraphClient,
    *,
    rule: dict[str, Any],
    triggers: list[dict],
    demographic_constraints: list[dict],
    aspect_lc: str,
    created_by: str,
    generator: GeneratorFn,
    pathway_index: int,
    pathway_total: int,
) -> ScaffoldResult:
    user_prompt = build_user_prompt(
        rule_id=rule["rule_id"],
        rule_label=(rule.get("rule_name") or "").strip() or rule["rule_id"],
        recommendation_text=rule.get("recommendation_text"),
        chapter_title=rule.get("chapter_title"),
        guideline_title=rule.get("guideline_title"),
        action_priority=rule.get("action_priority"),
        triggers=triggers,
        demographic_constraints=demographic_constraints,
    )
    draft = await generator(SYSTEM_PROMPT, user_prompt)
    if not isinstance(draft, dict) or "error" in draft:
        raise ScaffoldError(
            "AI scaffolder did not return JSON: "
            f"{draft.get('error') if isinstance(draft, dict) else draft!r}"
        )
    missing_keys = expected_field_set() - set(draft)
    if missing_keys:
        raise ScaffoldError(
            f"AI response missing required keys: {sorted(missing_keys)}."
        )

    demographics = _validate_demographics(
        draft.get("demographics") or {},
        demographic_constraints,
    )
    encounters = _validate_encounters(draft.get("encounters"), triggers)
    reviewer_focus = (draft.get("reviewer_focus") or "").strip()
    expected_sbar = (
        _expected_sbar_from_rule(rule, reviewer_focus)
        if aspect_lc == "summarisation"
        else None
    )

    display_hint = demographics["display_hint"]
    rule_friendly = _friendly_rule_label(rule)
    suffix = f" - pathway {pathway_index}" if pathway_total > 1 else ""
    name = (
        f"{display_hint}{suffix}"
        if display_hint
        else f"AI scaffold for {rule_friendly}{suffix}"
    )
    description = f"AI-scaffolded test patient for {rule_friendly}" + (
        f" ({rule.get('guideline_title')})" if rule.get("guideline_title") else ""
    )
    if pathway_total > 1:
        description = f"{description} - pathway {pathway_index} of {pathway_total}"

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

    # Stamp the AI provenance properties so the library can filter and
    # later show a "review AI drafts" badge. The properties live on the
    # root TestPatient node next to the existing source_patient_id
    # field used by the cross-graph clone.
    client.run(
        """
        MATCH (tp:TestPatient {id: $id, is_test: true})
        SET tp.aiAssisted    = true,
            tp.aiSourceKind  = 'rule',
            tp.aiSourceId    = $rule_id,
            tp.aiPromptVersion = 'test_patient_scaffold_v1',
            tp.generation_source = 'ai_scaffold_from_rule',
            tp.updated_at    = datetime()
        """,
        id=patient_id,
        rule_id=rule["rule_id"],
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

    return ScaffoldResult(
        patient_id=patient_id,
        patient_ids=[patient_id],
        aspect=aspect_lc,
        rule_id=rule["rule_id"],
        encounters_written=int(update.get("encounters_written") or 0),
        expected_sbar_written=bool(update.get("expected_sbar_written")),
        notes=(
            f"Scaffolded a {aspect_lc} test patient against {rule['rule_id']} "
            f"with {len(encounters)} encounter(s). Expected SBAR was "
            f"{'pre-filled' if expected_sbar else 'skipped (non-SBAR aspect)'} "
            "from the rule. Open the editor to review and edit before saving."
        ),
    )


def scaffold_patient_from_rule_sync(
    client: CodingGraphClient,
    *,
    rule_id: str,
    aspect: str = _DEFAULT_ASPECT_FOR_RULE,
    created_by: str = "",
    generator: GeneratorFn | None = None,
    draft_rule: dict[str, Any] | None = None,
) -> ScaffoldResult:
    """Synchronous entrypoint for FastAPI handlers.

    FastAPI's sync routes can't await directly; we run the coroutine
    in a fresh event loop so the rest of this module can stay async.
    """
    return asyncio.run(
        scaffold_patient_from_rule(
            client,
            rule_id=rule_id,
            aspect=aspect,
            created_by=created_by,
            generator=generator,
            draft_rule=draft_rule,
        )
    )
