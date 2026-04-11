"""Helper: reset and trace a single encounter run.

Uses the same trace path you shared:
- reset_encounter
- engine._get_all_plan_actions(...)
- engine.trace_run(actions, initial_state)
"""

from __future__ import annotations

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import (
    PatientGraphClient,
    get_async_driver,
    get_async_patient_driver,
)
from libs.workflow.engine import WorkflowEngine, WorkflowEvent
from app.services.reset_service import reset_encounter

DEFAULT_PATIENT_ID = os.environ.get("TRACE_PATIENT_ID", "4181221113")
DEFAULT_ENCOUNTER_ID = os.environ.get(
    "TRACE_ENCOUNTER_ID", "643b423a-bd67-4a1f-9b00-5337ca45b6dd"
)
DEFAULT_PLAN_DEFINITION_ID = os.environ.get("TRACE_PLAN_ID", "pd-gp-encounter-coding")


def _print_persisted_documents(*, patient_id: str, encounter_id: str) -> None:
    pg = PatientGraphClient()
    try:
        rows = pg.run(
            """
            MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter {id: $eid})-[r:DOCUMENTS]->(s)
            RETURN
              toString(s.conceptId) AS concept_id,
              coalesce(s.name, '') AS term,
              coalesce(r.evidence, '') AS evidence,
              r.value AS value,
              r.unit AS unit,
              r.confidence AS confidence,
              r.decision_tier AS decision_tier,
              r.context AS context
            ORDER BY confidence DESC
            """,
            pid=patient_id,
            eid=encounter_id,
        )
    finally:
        pg.close()
    print(json.dumps(rows, indent=2, default=str))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset and trace one encounter run.")
    parser.add_argument("--patient-id", default=DEFAULT_PATIENT_ID)
    parser.add_argument("--encounter-id", default=DEFAULT_ENCOUNTER_ID)
    parser.add_argument("--plan-id", default=DEFAULT_PLAN_DEFINITION_ID)
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    patient_id = str(args.patient_id)
    encounter_id = str(args.encounter_id)
    plan_definition_id = str(args.plan_id)

    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    load_keyvault_secrets()
    os.environ.setdefault("CODING_MODEL_PROVIDER_ENABLED", "true")

    print("=== RESET ===")
    pg = PatientGraphClient()
    try:
        with pg.session() as session:
            reset_result = reset_encounter(patient_id, encounter_id, session)
    finally:
        pg.close()
    print(json.dumps(reset_result, indent=2))

    async def run_trace() -> dict[str, Any]:
        kg_driver = get_async_driver()
        pg_driver = get_async_patient_driver()
        engine = WorkflowEngine(neo4j_driver=kg_driver, audit_neo4j_driver=pg_driver)
        try:
            actions = await engine._get_all_plan_actions(plan_definition_id)
            event = WorkflowEvent(
                event_type="encounter-created",
                patient_id=patient_id,
                encounter_id=encounter_id,
                plan_definition_id=plan_definition_id,
                context={
                    "encounter_id": encounter_id,
                    "plan_definition_id": plan_definition_id,
                    "mode": "extract_encounter",
                    "dry_run": False,
                    "trigger_analysis": True,
                },
            )
            initial_state = {
                "patient_id": event.patient_id,
                "encounter_id": event.encounter_id or "",
                "run_id": event.run_id,
                "errors": [],
                **event.context,
            }
            trace = await engine.trace_run(actions, initial_state)
        finally:
            await kg_driver.close()
            await pg_driver.close()
        return trace

    trace = await run_trace()

    print("=== TRACE STATUS ===")
    print(trace.get("status"))
    print("=== STEPS ===")
    for idx, step in enumerate(trace.get("steps", []), start=1):
        subgraph = step.get("subgraph_id")
        label = step.get("label")
        status = step.get("status")
        duration = step.get("duration_ms")
        output_state = step.get("output_state") or {}
        entities = output_state.get("entities")
        entity_count = len(entities) if isinstance(entities, list) else None
        msg = f"{idx:02d}. {label} [{subgraph}] status={status} duration_ms={duration}"
        if entity_count is not None:
            msg += f" entities={entity_count}"
        print(msg)
        if subgraph in {
            "post_processing",
            "extraction_check",
            "coding_check",
            "persist",
            "tier_classify",
        }:
            errors = output_state.get("errors") or []
            if errors:
                print("    errors:", errors)
    final_state = trace.get("final_state") or {}
    print("=== FINAL STATE ===")
    print("errors:", final_state.get("errors") or [])
    print("training_labels_written:", final_state.get("training_labels_written"))
    print("documents_written:", final_state.get("documents_written"))
    ents = final_state.get("entities") or []
    for idx, ent in enumerate(ents, start=1):
        value = ent.get("numeric_value")
        if value is None:
            value = ent.get("value")
        unit = ent.get("unit")
        line = (
            f"entity[{idx}] text={ent.get('text')} assertion={ent.get('assertion')} "
            f"tier={ent.get('tier')} reason={ent.get('tier_reason')} "
            f"llm_source={ent.get('_llm_check_source')} score={ent.get('score')} "
            f"value={value} unit={unit}"
        )
        print(line)

    print("=== PERSISTED DOCUMENTS ===")
    _print_persisted_documents(patient_id=patient_id, encounter_id=encounter_id)


if __name__ == "__main__":
    asyncio.run(main())
