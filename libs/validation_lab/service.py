"""Validation Lab application service (Neo4j-backed).

Atlas: DO-3A70C3DD
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from libs.cypher.validation_lab_queries import (
    GET_LAB_RUN,
    GET_VALIDATION_CASE,
    LIST_VALIDATION_CASES,
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
    poll_run_status,
    read_real_outputs,
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


def create_case(client: Any, spec: ValidationCaseSpec) -> dict[str, Any]:
    """Materialise graph + persist ValidationCase metadata."""
    graph = materialise_case(client, spec)
    client.run(
        UPSERT_VALIDATION_CASE,
        case_id=spec.case_id,
        title=spec.title,
        referral_text=spec.referral_text,
        pmh_json=_dumps([vars(item) for item in spec.pmh]),
        encounters_json=_dumps([vars(enc) for enc in spec.encounters]),
        patient_id=graph["patient_id"],
        encounter_id=graph.get("encounter_id") or "",
        referral_id=graph.get("referral_id") or "",
        document_reference_id=graph.get("document_reference_id") or "",
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
        out.append(case)
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
    case["runs"] = [dict(r) for r in (row.get("runs") or []) if r]
    for run in case["runs"]:
        run["outputs"] = _loads(run.pop("outputs_json", None))
    return case


def probe_graph_shape(client: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Return Neo4j shape evidence for VT assertions.

    Referral is the only submission shape now -- every case has exactly
    one referral document, so this always probes that shape.
    """
    rows = client.run(
        PROBE_REFERRAL_SHAPE,
        patient_id=case["patient_id"],
        referral_id=case.get("referral_id") or "",
        dr_id=case.get("document_reference_id") or "",
        encounter_id=case.get("encounter_id") or "",
    )
    return dict(rows[0]) if rows else {}


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
    is_terminal = outputs is not None or persist_mode is PersistMode.dry_run
    status = "completed" if is_terminal else "queued"
    client.run(
        UPSERT_LAB_RUN,
        case_id=case_id,
        run_id=run_id,
        persist_mode=persist_mode.value,
        plan_id=plan_id or case.get("plan_id") or "",
        phase_ids=list(phase_ids or []),
        status=status,
        outputs_json=_dumps(resolved.to_dict()),
        error_message="",
    )
    return get_run(client, case_id, run_id)


def _noop_publish(_body: dict[str, Any], _run_id: str) -> None:
    """Default in-process publish is a no-op; router may inject bus send."""
    return None


def get_run(client: Any, case_id: str, run_id: str) -> dict[str, Any]:
    rows = client.run(GET_LAB_RUN, case_id=case_id, run_id=run_id)
    if not rows:
        raise KeyError(f"ValidationLabRun not found: {run_id}")
    row = rows[0]
    run = dict(row["run"])
    run["outputs"] = _loads(run.pop("outputs_json", None))
    case = dict(row["case"])
    case["gold"] = _loads(case.pop("gold_json", None))
    return {"run": run, "case": case}


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
