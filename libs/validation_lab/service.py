"""Validation Lab application service (Neo4j-backed).

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DO-3A70C3DD
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from libs.cypher.validation_lab_queries import (
    DELETE_VALIDATION_CASE,
    GET_LAB_RUN,
    GET_VALIDATION_CASE,
    LIST_VALIDATION_CASES,
    PROBE_AG_SHAPE,
    PROBE_REFERRAL_SHAPE,
    SET_CASE_GOLD,
    UPDATE_VALIDATION_CASE,
    UPSERT_LAB_RUN,
    UPSERT_VALIDATION_CASE,
)
from libs.validation_lab.gold import (
    RunOutputs,
    promote_blocked_reason,
    score_against_gold,
)
from libs.validation_lab.models import PersistMode, ValidationCaseSpec
from libs.validation_lab.pipeline import (
    PublishFn,
    execute_lab_run,
    first_pipeline_error,
    poll_run_status,
    read_real_outputs,
)
from libs.validation_lab.ag_pipeline import (
    AgPipelineError,
    build_ag_pipeline_message,
    resolve_communication_request,
)
from libs.validation_lab.scaffold import materialise_case

JsonLoads = Callable[[str], Any]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, default=str)


def _loads(raw: Any) -> Any:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Convert Neo4j temporal values (and nested structures) for JSON responses."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    # neo4j.time.DateTime / Date / Time expose iso_format()
    if hasattr(value, "iso_format") and callable(value.iso_format):
        return value.iso_format()
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return value


def create_case(client: Any, spec: ValidationCaseSpec) -> dict[str, Any]:
    """Materialise graph + persist ValidationCase metadata."""
    graph = materialise_case(client, spec)
    gp_encounter = spec.gp_encounter
    client.run(
        UPSERT_VALIDATION_CASE,
        case_id=spec.case_id,
        title=spec.title,
        summary=str(spec.summary or "").strip()[:200],
        tags=[str(t).strip() for t in (spec.tags or []) if str(t).strip()][:8],
        referral_text=spec.referral_text,
        case_type=spec.case_type,
        scenario_type=spec.scenario_type or "generic",
        pmh_json=_dumps([vars(item) for item in spec.pmh]),
        encounters_json=_dumps([vars(enc) for enc in spec.encounters]),
        ag_thread_json=_dumps([vars(turn) for turn in spec.ag_thread]),
        ag_response_text=spec.ag_response_text or "",
        gp_encounter_json=_dumps(vars(gp_encounter) if gp_encounter else {}),
        reason_for_submission=spec.reason_for_submission or "",
        verbalisation_seed=spec.verbalisation_seed or spec.case_id,
        nhs_number=graph.get("nhs_number") or spec.nhs_number or "",
        gp_practice_name=spec.gp_practice_name or "",
        gp_encounter_id=graph.get("gp_encounter_id") or "",
        patient_id=graph["patient_id"],
        encounter_id=graph.get("encounter_id") or "",
        referral_id=graph.get("referral_id") or "",
        document_reference_id=graph.get("document_reference_id") or "",
        communication_request_id=graph.get("communication_request_id") or "",
        ubrn=graph.get("ubrn") or "",
        chunk_ids=list(graph.get("chunk_ids") or []),
        background_encounter_ids=list(graph.get("background_encounter_ids") or []),
        plan_id=spec.plan_id or "",
        gold_json=_dumps(spec.gold or {}),
        created_by=spec.created_by or "validation-lab",
    )
    return get_case(client, spec.case_id)


def list_cases(client: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = client.run(LIST_VALIDATION_CASES, limit=int(limit))
    out: list[dict[str, Any]] = []
    for row in rows:
        case = dict(row["case"]) if row.get("case") else {}
        out.append(_json_safe(case))
    return out


def get_case(client: Any, case_id: str) -> dict[str, Any]:
    rows = client.run(GET_VALIDATION_CASE, case_id=case_id)
    if not rows:
        raise KeyError(f"ValidationCase not found: {case_id}")
    row = rows[0]
    case = dict(row["case"])
    case["gold"] = _loads(case.pop("gold_json", None))
    case["pmh"] = _loads(case.pop("pmh_json", None)) or []
    case["encounters"] = _loads(case.pop("encounters_json", None)) or []
    case["ag_thread"] = _loads(case.pop("ag_thread_json", None)) or []
    case["gp_encounter"] = _loads(case.pop("gp_encounter_json", None)) or {}
    case["runs"] = [dict(r) for r in (row.get("runs") or []) if r]
    for run in case["runs"]:
        run["outputs"] = _loads(run.pop("outputs_json", None))
    return _json_safe(case)


def probe_graph_shape(client: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Return Neo4j shape evidence for VT assertions."""
    if case.get("case_type") == "ag" or case.get("communication_request_id"):
        rows = client.run(
            PROBE_AG_SHAPE,
            patient_id=case["patient_id"],
            communication_request_id=case.get("communication_request_id") or "",
        )
        return dict(rows[0]) if rows else {}
    rows = client.run(
        PROBE_REFERRAL_SHAPE,
        patient_id=case["patient_id"],
        referral_id=case.get("referral_id") or "",
        dr_id=case.get("document_reference_id") or "",
        encounter_id=case.get("encounter_id") or "",
    )
    return dict(rows[0]) if rows else {}


def preview_pmh_narrative(
    client: Any,
    *,
    pmh: list[dict[str, Any]],
    seed: str,
) -> dict[str, Any]:
    """Preview verbalised PMH for wizard confidence (knowledge graph read)."""
    from libs.neo4j_client.client import KnowledgeGraphClient
    from libs.validation_lab.models import PmhItem
    from libs.validation_lab.pmh_verbalisation import (
        load_verbalisation_pools,
        pick_verbalised_term,
        render_verbalised_pmh_narrative,
    )
    import random

    items = [
        PmhItem(
            category=row.get("category") or "condition",
            concept_id=str(row.get("concept_id") or ""),
            term=str(row.get("term") or ""),
        )
        for row in pmh
        if str(row.get("concept_id") or "").strip()
    ]
    kg = KnowledgeGraphClient()
    try:
        pools = load_verbalisation_pools(kg, [item.concept_id for item in items])
        narrative = render_verbalised_pmh_narrative(items, seed=seed, pools=pools)
        rng = random.Random(str(seed or "validation-lab"))
        terms_used = [
            {
                "concept_id": item.concept_id,
                "term": pick_verbalised_term(
                    item.concept_id,
                    pools=pools,
                    rng=rng,
                    fallback_term=item.term,
                ),
            }
            for item in items
        ]
    finally:
        kg.close()
    return {"narrative": narrative, "terms_used": terms_used}


def update_case(
    client: Any,
    case_id: str,
    *,
    title: str | None = None,
    referral_text: str | None = None,
    plan_id: str | None = None,
    gold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Patch case metadata and optional gold JSON (editor save)."""
    get_case(client, case_id)
    client.run(
        UPDATE_VALIDATION_CASE,
        case_id=case_id,
        title=title,
        referral_text=referral_text,
        plan_id=plan_id,
        gold_json=_dumps(gold) if gold is not None else None,
    )
    return get_case(client, case_id)


def delete_case(client: Any, case_id: str) -> dict[str, Any]:
    """Delete a ValidationCase, its lab runs, and the synthetic patient graph."""
    case = get_case(client, case_id)
    patient_id = str(case.get("patient_id") or "")
    client.run(DELETE_VALIDATION_CASE, case_id=case_id)
    if patient_id:
        from libs.validation_lab.scaffold import cleanup_case_graph

        cleanup_case_graph(patient_id)
    return {
        "deleted": True,
        "case_id": case_id,
        "patient_id": patient_id or None,
    }


def start_run(
    client: Any,
    *,
    case_id: str,
    plan_id: str,
    phase_ids: list[str],
    persist_mode: PersistMode = PersistMode.production,
    outputs: RunOutputs | None = None,
    publish: PublishFn | None = None,
    ruleset_version: str | None = None,
) -> dict[str, Any]:
    """Start a Lab run. Production mode only enqueues -- it never fabricates
    output. Poll with `refresh_run` for the real pipeline result."""
    case = get_case(client, case_id)
    run_id = uuid.uuid4().hex
    resolved = outputs or execute_lab_run(
        client,
        case=case,
        run_id=run_id,
        plan_id=plan_id or case.get("plan_id") or "",
        phase_ids=list(phase_ids or []),
        persist_mode=persist_mode,
        publish=publish if publish is not None else _noop_publish,
        ruleset_version=ruleset_version,
    )
    enqueue_error = ""
    if outputs is None and persist_mode is PersistMode.production:
        enqueue_error = first_pipeline_error(resolved)
    if enqueue_error:
        status = "failed"
    elif outputs is not None or persist_mode is PersistMode.dry_run:
        status = "completed"
    else:
        status = "queued"
    client.run(
        UPSERT_LAB_RUN,
        case_id=case_id,
        run_id=run_id,
        persist_mode=persist_mode.value,
        plan_id=plan_id or case.get("plan_id") or "",
        phase_ids=list(phase_ids or []),
        status=status,
        outputs_json=_dumps(resolved.to_dict()),
        error_message=enqueue_error[:500],
    )
    return get_run(client, case_id, run_id)


def _noop_publish(_body: dict[str, Any], _run_id: str) -> None:
    """Default in-process publish is a no-op; router may inject bus send."""
    return None


def start_ag_run(
    client: Any,
    *,
    ubrn: str,
    plan_id: str,
    phase_ids: list[str],
    persist_mode: PersistMode = PersistMode.production,
    publish: PublishFn | None = None,
    ruleset_version: str | None = None,
    guideline_id: str | None = None,
    completeness_domain: str | None = None,
    completeness_subdomain: str | None = None,
) -> dict[str, Any]:
    """Resolve an existing CommunicationRequest by ubrn and enqueue A&G run."""
    resolved = resolve_communication_request(client, ubrn)
    run_id = uuid.uuid4().hex
    dry = persist_mode is PersistMode.dry_run
    phase_outputs = [
        {
            "phase_id": p,
            "status": "skipped_persist" if dry else "queued",
            "persist_mode": persist_mode.value,
            "headline": f"Phase {p} ({persist_mode.value})",
        }
        for p in (phase_ids or ["extraction"])
    ]
    pipeline_enqueued = False
    pipeline_error = ""
    if not dry:
        body = build_ag_pipeline_message(
            patient_id=resolved["patient_id"],
            communication_request_id=resolved["communication_request_id"],
            ubrn=resolved["ubrn"],
            run_id=run_id,
            plan_definition_id=plan_id or "pd-referral-assessment",
            guideline_id=guideline_id,
            completeness_domain=completeness_domain,
            completeness_subdomain=completeness_subdomain,
            guideline_ruleset_version=ruleset_version,
            context={"source": "validation-lab-ag-run", "ubrn": resolved["ubrn"]},
            dry_run=False,
        )
        sender = publish if publish is not None else _noop_publish
        try:
            sender(body, run_id)
            pipeline_enqueued = True
        except Exception as exc:
            pipeline_error = str(exc)
        for row in phase_outputs:
            row["pipeline_enqueued"] = pipeline_enqueued
            if pipeline_error:
                row["pipeline_error"] = pipeline_error
    status = "completed" if dry else "queued"
    return {
        "run": {
            "id": run_id,
            "persist_mode": persist_mode.value,
            "status": status,
            "plan_id": plan_id,
            "phase_ids": list(phase_ids or []),
            "outputs": {"phase_outputs": phase_outputs},
        },
        "resolved": resolved,
    }


def refresh_ag_run(client: Any, run_id: str) -> dict[str, Any]:
    """Poll a standalone A&G run by run_id (same pipeline status source)."""
    status_info = poll_run_status(client, run_id)
    outputs = read_real_outputs(client, status_info.get("assessment_id") or "")
    return {
        "run": {
            "id": run_id,
            "status": status_info.get("status") or "queued",
            "outputs": outputs.to_dict(),
        }
    }


def get_run(client: Any, case_id: str, run_id: str) -> dict[str, Any]:
    rows = client.run(GET_LAB_RUN, case_id=case_id, run_id=run_id)
    if not rows:
        raise KeyError(f"ValidationLabRun not found: {run_id}")
    row = rows[0]
    run = dict(row["run"])
    run["outputs"] = _loads(run.pop("outputs_json", None))
    case = dict(row["case"])
    case["gold"] = _loads(case.pop("gold_json", None))
    return _json_safe({"run": run, "case": case})


def refresh_run(client: Any, case_id: str, run_id: str) -> dict[str, Any]:
    """Poll the real pipeline for a queued production run and persist the
    genuine result once it lands. A no-op for dry-run or already-terminal
    runs."""
    packed = get_run(client, case_id, run_id)
    run = packed["run"]
    if run.get("persist_mode") != PersistMode.production.value:
        return packed
    if run.get("status") in ("completed", "failed"):
        return packed
    status_info = poll_run_status(client, run_id)
    real_status = status_info["status"]
    if real_status not in ("completed", "failed"):
        return packed
    assessment_id = status_info["assessment_id"]
    outputs = read_real_outputs(client, assessment_id)
    prior_outputs = run.get("outputs") or {}
    outputs.phase_outputs = list(prior_outputs.get("phase_outputs") or [])
    client.run(
        UPSERT_LAB_RUN,
        case_id=case_id,
        run_id=run_id,
        persist_mode=run["persist_mode"],
        plan_id=run["plan_id"],
        phase_ids=run["phase_ids"],
        status=real_status,
        outputs_json=_dumps(outputs.to_dict()),
        error_message="",
    )
    return get_run(client, case_id, run_id)


def promote_gold(client: Any, case_id: str, run_id: str) -> dict[str, Any]:
    """Promote run outputs to case gold. Blocks dry-run."""
    packed = get_run(client, case_id, run_id)
    run = packed["run"]
    blocked = promote_blocked_reason(run.get("persist_mode") or "")
    if blocked:
        raise PermissionError(blocked)
    outputs = RunOutputs.from_dict(run.get("outputs") or {})
    gold = outputs.as_gold()
    client.run(SET_CASE_GOLD, case_id=case_id, gold_json=_dumps(gold.to_dict()))
    case = get_case(client, case_id)
    return {
        "case": case,
        "gold": gold.to_dict(),
        "promoted_from_run_id": run_id,
        "promoted_at": _iso_now(),
    }


def score_case_run(client: Any, case_id: str, run_id: str) -> dict[str, Any]:
    packed = get_run(client, case_id, run_id)
    gold = packed["case"].get("gold") or {}
    outputs = packed["run"].get("outputs") or {}
    return score_against_gold(gold, outputs)
