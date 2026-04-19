"""Persistence and replay logic for the reusable test-patient library.

A test patient is a synthetic profile (codes + age + sex + pathway) that
reviewers save against a guideline.  At save time we snapshot the
"expected" matched rules.  Every time the roaring-bitmap ruleset is
recompiled we replay the saved patients and report any drift.

This module is deliberately HTTP-thin: the FastAPI router translates
requests into calls against these functions, and these functions hide
the Neo4j/cypher and terminology-API plumbing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.db.neo4j_client import CodingGraphClient
from libs.cypher.test_patient_queries import (
    ASSERT_CONCEPTS_PRESENT,
    COUNT_TEST_PATIENTS_BY_ASPECT,
    CREATE_TEST_PATIENT,
    CREATE_TEST_PATIENT_FOR_ASPECT,
    DELETE_TEST_PATIENT,
    FIND_BY_CONTENT_HASH,
    GET_REPLAY_REPORT,
    GET_TEST_PATIENT,
    LIST_GUIDELINES_FOR_PICKER,
    LIST_REPLAY_REPORTS,
    LIST_RULES_FOR_PICKER,
    LIST_RULES_IN_SCOPE,
    LIST_TEST_PATIENTS,
    READ_TEST_PATIENT_FULL,
    RESET_TEST_PATIENT_CHILDREN,
    SEED_EXPECTED_SBAR,
    TEST_PATIENT_ASPECTS,
    UPDATE_TEST_PATIENT,
    UPDATE_TEST_PATIENT_PROFILE,
    WRITE_EDITOR_ENCOUNTER,
    WRITE_EXPECTED_RESULT,
    WRITE_REPLAY_REPORT,
)

logger = logging.getLogger(__name__)


TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001").rstrip(
    "/"
)
EVAL_TIMEOUT_S = float(os.getenv("TEST_PATIENT_EVAL_TIMEOUT", "30"))


@dataclass
class PatientPayload:
    """Minimal patient profile the dialog and generator both produce."""

    codes: list[str]
    age: float | None = None
    sex: str | None = None
    pathway_id: str | None = None
    name: str = ""
    description: str = ""
    generation_source: str = "manual"  # manual | generated | imported

    def normalised_codes(self) -> list[str]:
        return sorted({str(c).strip() for c in self.codes if str(c).strip()})

    def content_hash(self) -> str:
        """Deterministic dedup key per (codes, age, sex, pathway)."""
        payload = {
            "codes": self.normalised_codes(),
            "age": self.age,
            "sex": (self.sex or "").lower() or None,
            "pathway_id": self.pathway_id or None,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.blake2b(raw, digest_size=16).hexdigest()


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def list_guidelines_for_picker(client: CodingGraphClient) -> list[dict]:
    """Return guidelines that have at least one active rule."""
    return [dict(r) for r in client.run(LIST_GUIDELINES_FOR_PICKER)]


def list_rules_in_scope(
    client: CodingGraphClient,
    *,
    guideline_id: str | None = None,
    rule_id: str | None = None,
) -> list[dict]:
    rows = client.run(
        LIST_RULES_IN_SCOPE, guideline_id=guideline_id, rule_id=rule_id
    )
    return [dict(r) for r in rows]


def list_rules_for_picker(
    client: CodingGraphClient,
    *,
    guideline_id: str | None = None,
) -> list[dict]:
    """Plain-English picker payload for the SBAR Matched rule IDs field.

    Joins the rule with its Recommendation, Chapter, ActionGroup and the
    first three SNOMED criteria so the dropdown can show:
      - the verbatim NICE recommendation (a real sentence),
      - the chapter title (a familiar section reference),
      - the action priority (2ww / urgent / routine), and
      - up to three SNOMED triggers (a concrete cue).

    The reviewer never sees the raw rule_id unless they want to.
    """
    rows = client.run(LIST_RULES_FOR_PICKER, guideline_id=guideline_id)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Dry-run -- evaluate a patient against the live ruleset and walk each
# matched rule's logic tree to identify the satisfying branch nodes.
# ---------------------------------------------------------------------------


def evaluate_against_terminology(
    payload: PatientPayload,
    *,
    scope_type: str = "global",
    scope_id: str = "default",
    ruleset_version: str | None = None,
) -> dict:
    """Call POST /terminology/guidelines/evaluate and return its body.

    Returns ``{"matched_rules": [...], ...}`` on success.  Raises
    ``RuntimeError`` with a friendly message on failure so callers can
    surface a single error to the UI.
    """
    body = {
        "patient_codes": payload.normalised_codes(),
        "patient_age": payload.age,
        "patient_sex": payload.sex,
        "pathway_id": payload.pathway_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "ruleset_version": ruleset_version,
    }
    url = f"{TERMINOLOGY_API_URL}/terminology/guidelines/evaluate"
    try:
        with httpx.Client(timeout=EVAL_TIMEOUT_S) as http:
            resp = http.post(url, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Terminology API returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not reach the terminology API at {url}: {exc}"
        ) from exc


def compile_draft_ruleset(
    rules: list[dict],
    *,
    scope_id: str,
    policy_mode: str = "advisory",
    ttl_seconds: int = 1800,
) -> dict:
    """Compile UNSAVED draft rules into a sandbox bitmap ruleset.

    Proxies to the terminology API's ``/guidelines/bitmap/compile-draft``
    endpoint. Returns the version + scope so the caller can immediately
    evaluate patients against the sandbox. Raises ``RuntimeError`` with
    a friendly message on failure so callers can surface a single error
    to the UI.
    """
    body = {
        "rules": rules,
        "scope_id": scope_id,
        "policy_mode": policy_mode,
        "ttl_seconds": ttl_seconds,
    }
    url = f"{TERMINOLOGY_API_URL}/terminology/guidelines/bitmap/compile-draft"
    try:
        with httpx.Client(timeout=EVAL_TIMEOUT_S) as http:
            resp = http.post(url, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Terminology API returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not reach the terminology API at {url}: {exc}"
        ) from exc


def delete_sandbox_scope(scope_type: str, scope_id: str) -> dict:
    """Delete every Redis key for a sandbox scope.

    Failures are logged but never raised -- the sandbox bitmap will
    expire on its own thanks to the TTL applied at compile time, so
    a missed cleanup never leaves a permanent leak.
    """
    url = (
        f"{TERMINOLOGY_API_URL}/terminology/guidelines/scopes/"
        f"{scope_type}/{scope_id}"
    )
    try:
        with httpx.Client(timeout=EVAL_TIMEOUT_S) as http:
            resp = http.delete(url)
        if resp.status_code >= 400:
            logger.warning(
                "delete_sandbox_scope %s/%s returned %s: %s",
                scope_type,
                scope_id,
                resp.status_code,
                resp.text[:200],
            )
            return {"keys_deleted": 0}
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning(
            "delete_sandbox_scope %s/%s HTTP error: %s", scope_type, scope_id, exc
        )
        return {"keys_deleted": 0}


def sandbox_replay(
    client: CodingGraphClient,
    rules: list[dict],
    *,
    patient_ids: list[str] | None = None,
    guideline_id: str | None = None,
    sandbox_id: str | None = None,
    policy_mode: str = "advisory",
) -> dict:
    """Compile draft rules to a sandbox and replay saved patients.

    1. Compiles ``rules`` into a custom-scoped bitmap (no production
       collision is possible -- the compiler refuses ``global``).
    2. Replays each saved test patient through the standard evaluator
       against that sandbox scope (same code path production uses).
    3. Always cleans up the sandbox keys, even when the replay raises.
    """
    if not rules:
        raise RuntimeError("sandbox_replay requires at least one draft rule")
    sandbox_id = sandbox_id or f"draft-{uuid.uuid4().hex[:12]}"
    compile_summary = compile_draft_ruleset(
        rules,
        scope_id=sandbox_id,
        policy_mode=policy_mode,
    )
    try:
        report = replay_scope(
            client,
            patient_ids=patient_ids,
            guideline_id=guideline_id,
            scope_type="custom",
            scope_id=sandbox_id,
            ruleset_version=compile_summary.get("version"),
            persist_report=False,
        )
        # Bake per-regression diagnostics into the report WHILE the
        # sandbox bitmap is still alive.  After cleanup the dialog
        # cannot call /diagnose against this scope (404), so we
        # pre-compute the annotated trees here.
        _attach_regression_diagnostics(
            client,
            report,
            scope_type="custom",
            scope_id=sandbox_id,
            ruleset_version=compile_summary.get("version"),
        )
    finally:
        delete_sandbox_scope("custom", sandbox_id)
    return {
        "sandbox_id": sandbox_id,
        "compile": compile_summary,
        "report": report,
    }


def _attach_regression_diagnostics(
    client: CodingGraphClient,
    report: dict,
    *,
    scope_type: str,
    scope_id: str,
    ruleset_version: str | None,
) -> None:
    """Embed a per-regression ``diagnostic`` payload in the report.

    Mutates ``report`` in place.  Each regression in
    ``report["results"][i]["regressions"]`` gains a ``diagnostic``
    field carrying the same shape returned by the ``/diagnose``
    endpoint.  Failures are swallowed per regression so one bad
    rule cannot break the whole report.
    """
    for row in report.get("results") or []:
        regressions = row.get("regressions") or []
        if not regressions:
            continue
        patient = get_patient(client, patient_id=row.get("patient_id"))
        if not patient:
            continue
        payload = PatientPayload(
            codes=list(patient.get("codes") or []),
            age=patient.get("age"),
            sex=patient.get("sex"),
            pathway_id=patient.get("pathway_id"),
        )
        for regression in regressions:
            rid = regression.get("rule_id")
            if not rid:
                continue
            try:
                regression["diagnostic"] = diagnose_rule_against_patient(
                    payload,
                    rule_id=rid,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    ruleset_version=ruleset_version,
                )
            except RuntimeError as exc:
                logger.warning(
                    "diagnose for rule=%s patient=%s failed: %s",
                    rid,
                    row.get("patient_id"),
                    exc,
                )
                regression["diagnostic"] = None


def diagnose_rule_against_patient(
    payload: PatientPayload,
    *,
    rule_id: str,
    scope_type: str = "global",
    scope_id: str = "default",
    ruleset_version: str | None = None,
) -> dict:
    """Return per-node match diagnostics for ONE rule against a patient.

    Proxies to the terminology API's ``/diagnose`` endpoint so the
    answer is computed by the same bitmap evaluator that production
    uses to fire rules.  This guarantees the diagnostic verdict and
    the live firing decision agree.
    """
    body = {
        "rule_id": rule_id,
        "patient_codes": payload.normalised_codes(),
        "patient_age": payload.age,
        "patient_sex": payload.sex,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "ruleset_version": ruleset_version,
    }
    url = f"{TERMINOLOGY_API_URL}/terminology/guidelines/diagnose"
    try:
        with httpx.Client(timeout=EVAL_TIMEOUT_S) as http:
            resp = http.post(url, json=body)
        if resp.status_code == 404:
            # Forward the structured 404 detail (carries not_compiled,
            # rule_found, recompile_hint, scope_*) so the UI can render
            # a "Compile production ruleset" banner instead of a vague
            # error string.
            try:
                payload_in = resp.json() or {}
            except ValueError:
                payload_in = {}
            detail = payload_in.get("detail") if isinstance(payload_in, dict) else None
            if isinstance(detail, dict):
                return {
                    "rule_id": rule_id,
                    "fires": False,
                    "annotated_tree": None,
                    "rule_found": False,
                    "not_compiled": bool(detail.get("not_compiled")),
                    "message": detail.get(
                        "message", "Rule not found in active ruleset."
                    ),
                    "recompile_hint": detail.get("recompile_hint"),
                    "scope_type": detail.get("scope_type") or scope_type,
                    "scope_id": detail.get("scope_id") or scope_id,
                }
            raise RuntimeError(
                "Rule not found in active ruleset. The rule may need "
                "to be recompiled (POST /terminology/guidelines/bitmap/compile)."
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Terminology API returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not reach the terminology API at {url}: {exc}"
        ) from exc


def dry_run(
    client: CodingGraphClient,
    payload: PatientPayload,
    *,
    scope_type: str = "global",
    scope_id: str = "default",
    ruleset_version: str | None = None,
) -> dict:
    """Return ``{matched_rules, branch_paths}`` for the patient.

    ``branch_paths`` is a per-rule list of node_ids in that rule's
    logic tree that the patient currently satisfies.  This is what the
    UI uses to highlight "where the patient ended up".
    """
    eval_result = evaluate_against_terminology(
        payload,
        scope_type=scope_type,
        scope_id=scope_id,
        ruleset_version=ruleset_version,
    )
    matched_ids = [
        r.get("rule_id") for r in (eval_result.get("matched_rules") or [])
    ]
    branch_paths: dict[str, list[str]] = {}
    if matched_ids:
        rules = list_rules_in_scope(client)
        rules_by_id = {r["rule_id"]: r for r in rules}
        codes_set = set(payload.normalised_codes())
        for rid in matched_ids:
            row = rules_by_id.get(rid)
            if not row:
                continue
            tree = _parse_logic_json(row.get("logic_json"))
            if tree is None:
                continue
            branch_paths[rid] = _satisfied_node_ids(
                tree, codes_set, payload.age, payload.sex
            )
    return {
        "matched_rules": eval_result.get("matched_rules") or [],
        "branch_paths": branch_paths,
        "ruleset_version": eval_result.get("version")
        or eval_result.get("ruleset_version")
        or ruleset_version,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def find_existing(
    client: CodingGraphClient, *, guideline_id: str, content_hash: str
) -> str | None:
    rows = client.run(
        FIND_BY_CONTENT_HASH,
        guideline_id=guideline_id,
        content_hash=content_hash,
    )
    return rows[0]["id"] if rows else None


def confirm_and_save(
    client: CodingGraphClient,
    payload: PatientPayload,
    expectations: list[dict],
    *,
    guideline_id: str,
    scope_type: str,
    scope_id: str,
    created_by: str,
    ruleset_version: str | None = None,
    skip_if_exists: bool = True,
) -> dict:
    """Persist a TestPatient + EXPECTED_RESULT rels.

    ``expectations`` is the list the reviewer ticked, e.g.
    ``[{"rule_id": "r1", "fires": True, "matched_branch_node_ids": [...]}, ...]``.
    Returns ``{id, created, expectations_written}`` -- ``created`` is
    False when the patient already existed and ``skip_if_exists`` is True.
    """
    content_hash = payload.content_hash()
    if skip_if_exists:
        existing = find_existing(
            client, guideline_id=guideline_id, content_hash=content_hash
        )
        if existing:
            return {
                "id": existing,
                "created": False,
                "expectations_written": 0,
                "reason": "duplicate",
            }

    new_id = f"tp_{uuid.uuid4().hex[:12]}"
    client.run(
        CREATE_TEST_PATIENT,
        id=new_id,
        name=payload.name or _default_name(payload),
        description=payload.description or "",
        codes=payload.normalised_codes(),
        age=payload.age,
        sex=payload.sex,
        pathway_id=payload.pathway_id,
        scope_type=scope_type,
        scope_id=scope_id,
        generation_source=payload.generation_source,
        content_hash=content_hash,
        guideline_id=guideline_id,
        created_by=created_by,
    )

    written = 0
    for exp in expectations:
        rid = exp.get("rule_id")
        if not rid:
            continue
        client.run(
            WRITE_EXPECTED_RESULT,
            test_patient_id=new_id,
            rule_id=rid,
            fires=bool(exp.get("fires")),
            matched_branch_node_ids=list(exp.get("matched_branch_node_ids") or []),
            ruleset_version=ruleset_version or "",
            snapshot_by=created_by,
        )
        written += 1

    return {"id": new_id, "created": True, "expectations_written": written}


def list_patients(
    client: CodingGraphClient,
    *,
    aspect: str | None = None,
    guideline_id: str | None = None,
    rule_id: str | None = None,
    node_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return test patients matching the supplied filters.

    `aspect` is one of {"nlp","episodes","guidelines","summarisation"}
    or None / "all" for no aspect filter. Invalid aspect values fall
    back to "all" rather than raising, so the UI never 500s on a
    typo in a query string.
    """
    aspect_param: str | None
    if aspect is None or aspect == "" or aspect == "all":
        aspect_param = None
    elif aspect in TEST_PATIENT_ASPECTS:
        aspect_param = aspect
    else:
        aspect_param = None
    rows = client.run(
        LIST_TEST_PATIENTS,
        aspect=aspect_param,
        guideline_id=guideline_id,
        rule_id=rule_id,
        node_id=node_id,
        limit=limit,
    )
    return [dict(r) for r in rows]


def count_by_aspect(client: CodingGraphClient) -> dict[str, int]:
    """Return totals per aspect for the four count tiles.

    Always returns one entry per known aspect (zero when there are
    no patients for it), so the UI can render a stable four-tile
    layout without conditional rendering.
    """
    rows = client.run(COUNT_TEST_PATIENTS_BY_ASPECT)
    counts: dict[str, int] = {a: 0 for a in TEST_PATIENT_ASPECTS}
    for row in rows:
        aspect = str(row.get("aspect") or "").lower()
        if aspect in counts:
            counts[aspect] = int(row.get("total") or 0)
    counts["all"] = sum(counts.values())
    return counts


def get_patient(client: CodingGraphClient, *, patient_id: str) -> dict | None:
    rows = client.run(GET_TEST_PATIENT, id=patient_id)
    return dict(rows[0]) if rows else None


_NON_GUIDELINE_ASPECTS = {a for a in TEST_PATIENT_ASPECTS if a != "guidelines"}


def build_blank_patient_for_aspect(
    client: CodingGraphClient,
    *,
    aspect: str,
    name: str,
    description: str = "",
    age: float | None = None,
    sex: str | None = None,
    created_by: str = "",
) -> dict:
    """Create an empty :TestPatient row for an NLP / Episodes / SBAR aspect.

    The Guidelines aspect goes through the existing
    ``confirm_and_save`` flow because it must snapshot expected
    rule fires; this helper covers the three remaining aspects
    where the Build dialog only collects a name + demographics
    and the per-aspect content is attached later.
    """
    aspect_norm = (aspect or "").lower()
    if aspect_norm not in _NON_GUIDELINE_ASPECTS:
        raise ValueError(
            f"build_blank_patient_for_aspect supports {sorted(_NON_GUIDELINE_ASPECTS)}, "
            f"got {aspect!r}"
        )
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("name is required when building a test patient")
    safe_name = clean_name if clean_name.startswith("test_") else f"test_{clean_name}"
    payload = {
        "id": f"test_{uuid.uuid4().hex[:12]}",
        "name": safe_name,
        "description": (description or "").strip(),
        "aspect": aspect_norm,
        "source_patient_id": None,
        "generation_source": "manual",
        "age": age,
        "sex": (sex or "").strip().lower() or None,
        "created_by": (created_by or "").strip(),
    }
    rows = client.run(CREATE_TEST_PATIENT_FOR_ASPECT, **payload)
    if not rows:
        raise RuntimeError("create-test-patient query returned no rows")
    saved = {**payload, "id": rows[0]["id"]}
    return saved


def delete_patient(client: CodingGraphClient, *, patient_id: str) -> int:
    rows = client.run(DELETE_TEST_PATIENT, id=patient_id)
    return int(rows[0]["deleted"]) if rows else 0


# ---------------------------------------------------------------------------
# Per-aspect editor: GET /full + PATCH /full
# ---------------------------------------------------------------------------
#
# The Edit drawer in Knowledge > Test Patients reads and writes the
# whole editable subgraph in one shot:
#
#   :TestPatient                        -- root profile
#       -[:HAS_ENCOUNTER]-> :Encounter  -- free text + date + source label
#                       -[:DOCUMENTS]-> :Concept (term + assertion)
#       -[:HAS_EXPECTED_SBAR]-> :ExpectedSBAR (S/B/A/R + phrases)
#
# Concepts are MERGE'd against pre-loaded :Concept nodes (no concept
# is ever created by the editor). The pre-flight ASSERT_CONCEPTS_PRESENT
# call mirrors the cross-graph clone guarantee -- we never write a
# DOCUMENTS edge to a SNOMED id that is not already in the graph.


class EditorError(ValueError):
    """Raised when the editor cannot apply an update (missing concept,
    blank name, etc.). Translates to HTTP 4xx in the router."""


def get_full_patient(
    client: CodingGraphClient, *, patient_id: str
) -> dict | None:
    """Read the entire editable subgraph for one test patient.

    Returns ``None`` when no patient with that id is found, otherwise
    the full editable shape: root profile + encounters (with codes)
    + optional expected SBAR for the summarisation aspect.
    """
    rows = client.run(READ_TEST_PATIENT_FULL, id=patient_id)
    if not rows:
        return None
    row = dict(rows[0])
    row["encounters"] = list(row.get("encounters") or [])
    return row


def _normalise_codes(codes: list[dict] | None) -> list[dict]:
    """Filter and normalise the editor's per-encounter code list."""
    if not codes:
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for code in codes:
        cid = str((code or {}).get("concept_id") or "").strip()
        if not cid:
            continue
        assertion = str(
            (code or {}).get("assertion") or "present"
        ).strip().lower() or "present"
        key = (cid, assertion)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "concept_id": cid,
                "term": (code.get("term") or "").strip() or None,
                "assertion": assertion,
            }
        )
    return out


def _collect_concept_ids_from_encounters(
    encounters: list[dict],
) -> list[str]:
    """Return every distinct SNOMED id referenced by the encounter list."""
    ids: set[str] = set()
    for enc in encounters or []:
        for code in enc.get("codes") or []:
            cid = code.get("concept_id")
            if cid:
                ids.add(str(cid))
    return sorted(ids)


def _assert_editor_concepts_present(
    client: CodingGraphClient, concept_ids: list[str]
) -> None:
    """Loud failure when any expected SNOMED id is missing.

    Mirrors the cross-graph clone behaviour so the editor cannot
    silently MERGE against a non-existent concept (which would
    otherwise create an empty placeholder node and corrupt every
    downstream NLP / SBAR scoring run).
    """
    if not concept_ids:
        return
    rows = client.run(ASSERT_CONCEPTS_PRESENT, concept_ids=concept_ids)
    missing = (rows[0].get("missing") if rows else []) or []
    if missing:
        raise EditorError(
            "Cannot save: the knowledge graph is missing "
            f"{len(missing)} SNOMED concept(s) referenced by the "
            "editor: " + ", ".join(sorted(missing))
        )


def _write_editor_encounters(
    client: CodingGraphClient,
    *,
    patient_id: str,
    encounters: list[dict],
) -> int:
    """Write each editor-supplied encounter under the test patient."""
    written = 0
    for index, enc in enumerate(encounters or [], start=1):
        encounter_id = (
            (enc.get("id") or f"{patient_id}_enc_{index:03d}").strip()
        )
        client.run(
            WRITE_EDITOR_ENCOUNTER,
            tp_id=patient_id,
            encounter_id=encounter_id,
            source_label=(enc.get("source_label") or "").strip() or None,
            source_id=(enc.get("source_id") or "").strip() or None,
            text=(enc.get("text") or ""),
            date=(enc.get("date") or None),
            codes=_normalise_codes(enc.get("codes")),
        )
        written += 1
    return written


def _write_expected_sbar(
    client: CodingGraphClient,
    *,
    patient_id: str,
    expected: dict | None,
) -> bool:
    """Write or refresh the :ExpectedSBAR for a summarisation patient.

    Returns True when an ExpectedSBAR was written, False when the
    caller passed ``None`` (i.e. clear the expected SBAR).
    """
    if not expected:
        return False
    sbar_id = str(
        expected.get("id") or f"{patient_id}_expected_sbar"
    ).strip()
    client.run(
        SEED_EXPECTED_SBAR,
        tp_id=patient_id,
        sbar_id=sbar_id,
        fixture_id=expected.get("fixture_id"),
        situation_md=expected.get("situation_md") or "",
        background_md=expected.get("background_md") or "",
        recommendation_md=expected.get("recommendation_md") or "",
        matched_rule_ids=list(expected.get("matched_rule_ids") or []),
        required_phrases=list(expected.get("required_phrases") or []),
        banned_phrases=list(expected.get("banned_phrases") or []),
        expected_action_priority=expected.get("expected_action_priority"),
        reviewer_focus=expected.get("reviewer_focus") or "",
        evaluator_outage=bool(expected.get("evaluator_outage", False)),
    )
    return True


_GUIDELINES_ASPECT = "guidelines"


def update_full_patient(
    client: CodingGraphClient,
    *,
    patient_id: str,
    aspect: str,
    name: str,
    description: str = "",
    age: float | None = None,
    sex: str | None = None,
    encounters: list[dict] | None = None,
    expected_sbar: dict | None = None,
    updated_by: str = "",
) -> dict:
    """Replace the editable subgraph for one test patient atomically.

    Steps (in this order):

    1. Validate the patient exists. Returns ``{updated: False}`` when
       not, so the router can translate that to a 404.
    2. Pre-flight every SNOMED concept referenced by the encounters
       against the knowledge graph. Raises :class:`EditorError` on any
       missing id (loud failure -- never MERGE blindly).
    3. Update the root profile (name / description / age / sex).
    4. Detach + delete every editor-managed child node (encounters,
       documents, expected SBAR) so the next step writes a clean
       subgraph.
    5. Re-create the encounter list and (for summarisation) the
       expected SBAR row.

    The Guidelines aspect is rejected at this entry point because its
    rule-fire snapshot lives on EXPECTED_RESULT relationships under
    ``UPDATE_TEST_PATIENT`` / ``WRITE_EXPECTED_RESULT``. Editing
    Guidelines test patients should continue to flow through the
    existing ``update_patient`` service so the snapshot is preserved.
    """
    aspect_norm = (aspect or "").strip().lower()
    if aspect_norm == _GUIDELINES_ASPECT:
        raise EditorError(
            "Guidelines aspect uses update_patient (rule-fire snapshot)."
        )
    if aspect_norm not in TEST_PATIENT_ASPECTS:
        raise EditorError(
            f"Aspect must be one of {sorted(TEST_PATIENT_ASPECTS)}."
        )
    clean_name = (name or "").strip()
    if not clean_name:
        raise EditorError("Give the test patient a short name first.")
    safe_name = clean_name if clean_name.startswith("test_") else f"test_{clean_name}"

    encounters = list(encounters or [])
    concept_ids = _collect_concept_ids_from_encounters(encounters)
    _assert_editor_concepts_present(client, concept_ids)

    root_rows = client.run(
        UPDATE_TEST_PATIENT_PROFILE,
        id=patient_id,
        name=safe_name,
        description=(description or "").strip(),
        age=age,
        sex=(sex or "").strip().lower() or None,
        updated_by=(updated_by or "").strip(),
    )
    if not root_rows:
        return {
            "id": patient_id,
            "updated": False,
            "encounters_written": 0,
            "expected_sbar_written": False,
        }

    client.run(RESET_TEST_PATIENT_CHILDREN, id=patient_id)
    encounters_written = _write_editor_encounters(
        client, patient_id=patient_id, encounters=encounters
    )
    expected_written = False
    if aspect_norm == "summarisation":
        expected_written = _write_expected_sbar(
            client, patient_id=patient_id, expected=expected_sbar
        )
    return {
        "id": patient_id,
        "updated": True,
        "aspect": aspect_norm,
        "encounters_written": encounters_written,
        "expected_sbar_written": expected_written,
    }


def update_patient(
    client: CodingGraphClient,
    *,
    patient_id: str,
    payload: PatientPayload,
    expectations: list[dict],
    updated_by: str,
    ruleset_version: str | None = None,
) -> dict:
    """Update a saved test patient's profile and replace its expectations.

    Updates name / description / codes / age / sex / pathway_id /
    content_hash on the TestPatient node, deletes every existing
    EXPECTED_RESULT relationship, then writes the supplied
    ``expectations`` afresh.  Empty expectation list is allowed (the
    patient is left with no assertions, which makes replay a no-op
    for that patient -- the UI surfaces this as "no assertions").

    Returns ``{id, updated, expectations_written}``.  When the
    patient does not exist ``updated`` is False and the caller (the
    router) translates that into a 404.
    """
    rows = client.run(
        UPDATE_TEST_PATIENT,
        id=patient_id,
        name=payload.name or _default_name(payload),
        description=payload.description or "",
        codes=payload.normalised_codes(),
        age=payload.age,
        sex=payload.sex,
        pathway_id=payload.pathway_id,
        content_hash=payload.content_hash(),
        updated_by=updated_by,
    )
    if not rows:
        return {"id": patient_id, "updated": False, "expectations_written": 0}
    written = 0
    for exp in expectations:
        rid = exp.get("rule_id")
        if not rid:
            continue
        client.run(
            WRITE_EXPECTED_RESULT,
            test_patient_id=patient_id,
            rule_id=rid,
            fires=bool(exp.get("fires")),
            matched_branch_node_ids=list(
                exp.get("matched_branch_node_ids") or []
            ),
            ruleset_version=ruleset_version or "",
            snapshot_by=updated_by,
        )
        written += 1
    return {
        "id": patient_id,
        "updated": True,
        "expectations_written": written,
    }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def diff_replay(
    expectations: list[dict], current_matches: list[dict]
) -> dict:
    """Compare a saved snapshot to a fresh evaluation result.

    Buckets each expectation into one of:
      - pass:        rule asserted to fire and now fires (or vice versa)
      - regression:  rule asserted to fire and now doesn't (or vice versa)
      - drift:       branch_paths changed but fires/doesn't_fire is unchanged
    Unasserted matches surface in ``unexpected_matches`` for visibility.
    """
    matched_ids = {m.get("rule_id") for m in current_matches}
    asserted_ids = {e.get("rule_id") for e in expectations}
    passes, regressions = [], []
    for exp in expectations:
        rid = exp.get("rule_id")
        expected_fires = bool(exp.get("fires"))
        actual_fires = rid in matched_ids
        if expected_fires == actual_fires:
            passes.append(
                {"rule_id": rid, "fires": actual_fires, "expected": expected_fires}
            )
        else:
            regressions.append(
                {"rule_id": rid, "fires": actual_fires, "expected": expected_fires}
            )
    unexpected = [
        m for m in current_matches if m.get("rule_id") not in asserted_ids
    ]
    return {
        "passes": passes,
        "regressions": regressions,
        "unexpected_matches": unexpected,
        "total_assertions": len(expectations),
    }


def replay_one(
    client: CodingGraphClient,
    patient_row: dict,
    *,
    scope_type: str = "global",
    scope_id: str = "default",
    ruleset_version: str | None = None,
) -> dict:
    """Re-evaluate one saved patient and diff against its snapshot."""
    payload = PatientPayload(
        codes=list(patient_row.get("codes") or []),
        age=patient_row.get("age"),
        sex=patient_row.get("sex"),
        pathway_id=patient_row.get("pathway_id"),
    )
    try:
        eval_result = evaluate_against_terminology(
            payload,
            scope_type=scope_type,
            scope_id=scope_id,
            ruleset_version=ruleset_version,
        )
    except RuntimeError as exc:
        return {
            "patient_id": patient_row.get("id"),
            "patient_name": patient_row.get("name"),
            "error": str(exc),
            "passes": [],
            "regressions": [],
            "unexpected_matches": [],
            "total_assertions": len(patient_row.get("expectations") or []),
        }
    diff = diff_replay(
        list(patient_row.get("expectations") or []),
        list(eval_result.get("matched_rules") or []),
    )
    return {
        "patient_id": patient_row.get("id"),
        "patient_name": patient_row.get("name"),
        **diff,
    }


def replay_scope(
    client: CodingGraphClient,
    *,
    guideline_id: str | None = None,
    patient_ids: list[str] | None = None,
    scope_type: str = "global",
    scope_id: str = "default",
    ruleset_version: str | None = None,
    persist_report: bool = True,
) -> dict:
    """Replay all patients in scope and (optionally) persist the report."""
    if patient_ids:
        rows = []
        for pid in patient_ids:
            row = get_patient(client, patient_id=pid)
            if row:
                rows.append(row)
    else:
        rows = list_patients(client, guideline_id=guideline_id)

    per_patient = [
        replay_one(
            client,
            row,
            scope_type=scope_type,
            scope_id=scope_id,
            ruleset_version=ruleset_version,
        )
        for row in rows
    ]
    regressions_count = sum(len(p["regressions"]) for p in per_patient)
    passes_count = sum(len(p["passes"]) for p in per_patient)
    drift_count = sum(1 for p in per_patient if p.get("unexpected_matches"))
    report = {
        "ruleset_version": ruleset_version,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "guideline_id": guideline_id,
        "patient_count": len(rows),
        "regressions_count": regressions_count,
        "passes_count": passes_count,
        "drift_count": drift_count,
        "results": per_patient,
    }
    if persist_report:
        report["id"] = _persist_replay_report(client, report)
    return report


def _persist_replay_report(client: CodingGraphClient, report: dict) -> str:
    rid = f"rv_{uuid.uuid4().hex[:12]}"
    client.run(
        WRITE_REPLAY_REPORT,
        id=rid,
        ruleset_version=report.get("ruleset_version") or "",
        scope_type=report.get("scope_type") or "global",
        scope_id=report.get("scope_id") or "default",
        guideline_id=report.get("guideline_id") or "",
        report_json=json.dumps(report),
        regressions_count=int(report.get("regressions_count") or 0),
        passes_count=int(report.get("passes_count") or 0),
        drift_count=int(report.get("drift_count") or 0),
        total_count=int(report.get("patient_count") or 0),
    )
    return rid


def list_replay_reports(
    client: CodingGraphClient,
    *,
    guideline_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    rows = client.run(
        LIST_REPLAY_REPORTS,
        guideline_id=guideline_id,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
    )
    return [dict(r) for r in rows]


def get_replay_report(client: CodingGraphClient, *, report_id: str) -> dict | None:
    rows = client.run(GET_REPLAY_REPORT, id=report_id)
    if not rows:
        return None
    row = dict(rows[0])
    raw_json = row.get("report_json")
    try:
        row["report"] = json.loads(raw_json) if raw_json else {}
    except Exception:
        row["report"] = {}
    return row


# ---------------------------------------------------------------------------
# Logic-tree helpers (mirrors the editor's tree shape)
# ---------------------------------------------------------------------------


def _parse_logic_json(value: Any) -> dict | None:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _satisfied_node_ids(
    node: dict | None,
    codes: set[str],
    age: float | None,
    sex: str | None,
) -> list[str]:
    """Walk the logic tree and return ids of nodes the patient satisfies."""
    out: list[str] = []
    _walk_satisfied(node, codes, age, sex, out)
    return out


def _walk_satisfied(
    node: dict | None,
    codes: set[str],
    age: float | None,
    sex: str | None,
    acc: list[str],
) -> bool:
    if not isinstance(node, dict):
        return False
    kind = str(node.get("kind") or "").upper()
    node_id = node.get("node_id") or node.get("id")

    if kind == "CONCEPT":
        criterion = node.get("criterion") or {}
        cid = str(criterion.get("snomed_concept_id") or "")
        ok = cid in codes
        if ok and node_id:
            acc.append(node_id)
        return ok

    if kind == "DEMOGRAPHIC":
        ok = _check_demographic(node, age, sex)
        if ok and node_id:
            acc.append(node_id)
        return ok

    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    child_ok = [_walk_satisfied(c, codes, age, sex, acc) for c in children]

    if kind == "AND":
        ok = bool(children) and all(child_ok)
    elif kind == "OR":
        ok = any(child_ok)
    elif kind == "NOT":
        ok = bool(children) and not child_ok[0]
    elif kind == "AT_LEAST":
        min_n = int(node.get("min") or 1)
        ok = sum(1 for x in child_ok if x) >= min_n
    else:
        ok = False

    if ok and node_id:
        acc.append(node_id)
    return ok


def _check_demographic(node: dict, age: float | None, sex: str | None) -> bool:
    field = str(node.get("field") or "").lower()
    operator = str(node.get("operator") or "").lower()
    raw_value = node.get("value")
    if field == "age":
        if age is None or raw_value is None:
            return False
        try:
            target = float(raw_value)
        except (TypeError, ValueError):
            return False
        return _compare_number(float(age), operator, target)
    if field == "sex":
        if not sex or raw_value is None:
            return False
        return str(sex).lower() == str(raw_value).lower()
    return False


def _compare_number(value: float, operator: str, target: float) -> bool:
    if operator in (">=", "gte"):
        return value >= target
    if operator in (">", "gt"):
        return value > target
    if operator in ("<=", "lte"):
        return value <= target
    if operator in ("<", "lt"):
        return value < target
    if operator in ("==", "=", "eq"):
        return value == target
    if operator in ("!=", "ne"):
        return value != target
    return False


def _default_name(payload: PatientPayload) -> str:
    bits = []
    if payload.age is not None:
        bits.append(f"{int(payload.age)}y")
    if payload.sex:
        bits.append(payload.sex.title())
    if payload.codes:
        bits.append(f"{len(payload.codes)} codes")
    return ", ".join(bits) or "Unnamed test patient"
