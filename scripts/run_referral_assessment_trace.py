"""Run the production referral assessment workflow for extraction scenarios."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import (
    KnowledgeGraphClient,
    PatientGraphClient,
    get_async_driver,
    get_async_patient_driver,
)
from libs.workflow.engine import WorkflowEngine

DEFAULT_CASES = ["lower_gi_letter_001"]
DEFAULT_PLAN_ID = "pd-referral-assessment"
DEFAULT_GUIDELINE_ID = "NG12"
DEFAULT_DOMAIN = "cancer_referrals"
DEFAULT_SUBDOMAIN = "lower_gi"
UPPER_GI_SUBDOMAIN = "upper_gi"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace referral assessment.")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--plan-id", default=DEFAULT_PLAN_ID)
    parser.add_argument("--patient-prefix", default="trace-lower-gi")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--guideline-id", default=DEFAULT_GUIDELINE_ID)
    parser.add_argument("--completeness-domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--completeness-subdomain", default=DEFAULT_SUBDOMAIN)
    parser.add_argument("--configure-lower-gi-defaults", action="store_true")
    parser.add_argument("--configure-upper-gi-defaults", action="store_true")
    parser.add_argument("--durable", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args()


def _load_case(case_id: str) -> dict[str, Any]:
    path = ROOT / "tests/fixtures/clinical_extraction_scenarios/expected_strings.json"
    data = json.loads(path.read_text())
    for case in data.get("cases", []):
        if case.get("case_id") == case_id:
            source = ROOT / str(case["source_markdown"])
            return {**case, "markdown_body": source.read_text()}
    raise KeyError(f"Unknown extraction scenario case_id={case_id}")


def _upsert_fixture_encounter(
    *, patient_id: str, encounter_id: str, case_id: str, text: str
) -> None:
    client = PatientGraphClient()
    try:
        client.run(
            "MERGE (p:Patient {id: $patient_id}) "
            "SET p.source = 'workflow_trace' "
            "MERGE (e:Encounter {id: $encounter_id}) "
            "SET e.text = $text, e.case_id = $case_id, "
            "    e.source = 'clinical_extraction_scenario' "
            "MERGE (p)-[:HAS_ENCOUNTER]->(e)",
            patient_id=patient_id,
            encounter_id=encounter_id,
            case_id=case_id,
            text=text,
        )
    finally:
        client.close()


def _lower_gi_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "FIT result",
            "required": True,
            "semantic_categories": [],
            "concept_ids": [71711000112103],
        },
        {
            "name": "Blood results",
            "required": True,
            "semantic_categories": ["observable_entity"],
            "concept_ids": [],
        },
        {
            "name": "Presenting symptom",
            "required": True,
            "semantic_categories": ["finding", "disorder"],
            "concept_ids": [],
        },
    ]


def _upper_gi_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "Blood results",
            "required": True,
            "semantic_categories": ["observable_entity"],
            "concept_ids": [],
        },
        {
            "name": "Presenting symptom",
            "required": True,
            "semantic_categories": ["finding", "disorder"],
            "concept_ids": [],
        },
    ]


def _configure_site_completeness(
    *,
    subdomain: str,
    valueset_id: str,
    title: str,
    schema: list[dict[str, Any]],
) -> None:
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (d:AuditDomain {id: $domain}) "
            "SET d.name = 'Cancer referrals', d.source = 'tenant' "
            "MERGE (v:ValueSet {id: $valueset}) "
            "SET v.name = $subdomain, v.title = $title, "
            "    v.completeness_schema = $schema, "
            "    v.completeness_schema_active = true, "
            "    v.completeness_schema_updated_at = datetime() "
            "MERGE (d)-[:HAS_SUBDOMAIN]->(v)",
            domain=DEFAULT_DOMAIN,
            valueset=valueset_id,
            subdomain=subdomain,
            title=title,
            schema=json.dumps(schema, sort_keys=True),
        )
    finally:
        client.close()


def _configure_lower_gi_completeness() -> None:
    _configure_site_completeness(
        subdomain=DEFAULT_SUBDOMAIN,
        valueset_id="ncda-lower-gi",
        title="Lower GI",
        schema=_lower_gi_schema(),
    )


def _configure_upper_gi_completeness() -> None:
    _configure_site_completeness(
        subdomain=UPPER_GI_SUBDOMAIN,
        valueset_id="ncda-upper-gi",
        title="Upper GI",
        schema=_upper_gi_schema(),
    )


async def _compile_guideline(guideline_id: str) -> dict[str, Any]:
    from services.terminology_api.app.services.guideline_compiler import (
        CompileScope,
        GuidelineCompiler,
    )

    version = f"trace-{guideline_id.lower()}-{int(time.time())}"
    return await GuidelineCompiler().compile_and_store(
        version,
        scope=CompileScope.from_values("guideline", guideline_id),
    )


def _state_for_case(
    *,
    case: dict[str, Any],
    patient_id: str,
    encounter_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_type": "referral-received",
        "plan_definition_id": args.plan_id,
        "run_id": f"trace-{case['case_id']}-{int(time.time())}",
        "case_id": case["case_id"],
        "encounter_text": case["markdown_body"],
        "source_node_type": "ExtractionScenario",
        "source_node_id": case["case_id"],
        "source_text_property": "markdown_body",
        "mode": "referral_assessment",
        "output_target": "patient_graph",
        "dry_run": bool(args.dry_run),
        "guideline_scope_type": "guideline",
        "guideline_scope_id": args.guideline_id,
        "guideline_id": args.guideline_id,
        "completeness_domain": args.completeness_domain,
        "completeness_subdomain": args.completeness_subdomain,
        "errors": [],
    }


async def _run_trace(initial_state: dict[str, Any], plan_id: str) -> dict[str, Any]:
    kg_driver = get_async_driver()
    pg_driver = get_async_patient_driver()
    engine = WorkflowEngine(neo4j_driver=kg_driver, audit_neo4j_driver=pg_driver)
    try:
        actions = await engine._get_all_plan_actions(plan_id)
        if not actions:
            raise RuntimeError(f"No actions found for PlanDefinition {plan_id}")
        return await engine.trace_run(actions, initial_state)
    finally:
        await kg_driver.close()
        await pg_driver.close()


async def _run_durable_trace(initial_state: dict[str, Any]) -> dict[str, Any]:
    from services.pipeline_worker.app.services.referral_durable_steps import (
        REFERRAL_STEPS,
        handle_referral_durable_message,
    )

    steps: list[dict[str, Any]] = []
    for definition in REFERRAL_STEPS:
        body = {
            **initial_state,
            "event_type": definition.event_type,
            "workflow_id": DEFAULT_PLAN_ID,
            "step_id": definition.step_id,
            "context": initial_state,
        }
        started = time.time()
        try:
            result = await handle_referral_durable_message(
                body,
                bus=None,
                publish_progress=None,
            )
            steps.append(
                {
                    "step_id": definition.step_id,
                    "subgraph_id": definition.subgraph_id or "sbar_orchestrator",
                    "label": definition.event_type,
                    "status": result.status,
                    "duration_ms": int((time.time() - started) * 1000),
                    "output_state": result.output,
                }
            )
            if result.status != "completed":
                return {"status": result.status, "steps": steps}
        except Exception as exc:
            steps.append(
                {
                    "step_id": definition.step_id,
                    "subgraph_id": definition.subgraph_id or "sbar_orchestrator",
                    "label": definition.event_type,
                    "status": "failed",
                    "duration_ms": int((time.time() - started) * 1000),
                    "output_state": {"errors": [str(exc)]},
                }
            )
            return {"status": "failed", "steps": steps}
    return {"status": "completed", "steps": steps}


def _compact_step(step: dict[str, Any]) -> dict[str, Any]:
    state = step.get("output_state") or {}
    return {
        "step_id": step.get("step_id"),
        "subgraph_id": step.get("subgraph_id"),
        "label": step.get("label"),
        "status": step.get("status"),
        "duration_ms": step.get("duration_ms"),
        "entity_count": len(state.get("entities") or []),
        "errors": state.get("errors") or [],
        "guideline_result": state.get("guideline_result"),
        "completeness_result": state.get("completeness_result"),
        "sbar_report": state.get("sbar_report"),
        "documents_written": state.get("documents_written"),
        "review_status": state.get("review_status"),
    }


def _print_persisted_documents(patient_id: str, encounter_id: str) -> list[dict]:
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->"
            "(:Encounter {id: $encounter_id})-[r:DOCUMENTS]->(s) "
            "RETURN toString(s.conceptId) AS concept_id, "
            "       coalesce(s.name, '') AS term, "
            "       coalesce(r.evidence, '') AS evidence, "
            "       r.confidence AS confidence "
            "ORDER BY confidence DESC",
            patient_id=patient_id,
            encounter_id=encounter_id,
        )
    finally:
        client.close()
    return rows


async def _run_case(args: argparse.Namespace, case_id: str) -> dict[str, Any]:
    case = _load_case(case_id)
    patient_id = f"{args.patient_prefix}-{case_id}"
    encounter_id = f"{case_id}-encounter"
    if not args.dry_run:
        _upsert_fixture_encounter(
            patient_id=patient_id,
            encounter_id=encounter_id,
            case_id=case_id,
            text=case["markdown_body"],
        )
    state = _state_for_case(
        case=case,
        patient_id=patient_id,
        encounter_id=encounter_id,
        args=args,
    )
    trace = (
        await _run_durable_trace(state)
        if args.durable
        else await _run_trace(state, args.plan_id)
    )
    persisted = (
        [] if args.dry_run else _print_persisted_documents(patient_id, encounter_id)
    )
    return {
        "case_id": case_id,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "mode": "durable_pubsub" if args.durable else "legacy_in_process",
        "status": trace.get("status"),
        "steps": [_compact_step(step) for step in trace.get("steps", [])],
        "final_errors": (trace.get("final_state") or {}).get("errors") or [],
        "persisted_documents": persisted,
    }


async def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    load_keyvault_secrets()
    os.environ.setdefault("CODING_MODEL_PROVIDER_ENABLED", "true")

    setup: dict[str, Any] = {}
    if args.configure_lower_gi_defaults:
        _configure_lower_gi_completeness()
        setup["completeness_seeded"] = DEFAULT_SUBDOMAIN
    if args.configure_upper_gi_defaults:
        _configure_upper_gi_completeness()
        setup["completeness_seeded"] = UPPER_GI_SUBDOMAIN
    if args.configure_lower_gi_defaults or args.configure_upper_gi_defaults:
        try:
            setup["guideline_compile"] = await _compile_guideline(args.guideline_id)
        except Exception as exc:
            setup["guideline_compile_error"] = str(exc)

    case_ids = args.case_ids or DEFAULT_CASES
    runs = [await _run_case(args, case_id) for case_id in case_ids]
    result = {"setup": setup, "runs": runs}
    text = json.dumps(result, indent=2, default=str)
    print(text)
    if args.output:
        Path(args.output).write_text(text)


if __name__ == "__main__":
    asyncio.run(main())
