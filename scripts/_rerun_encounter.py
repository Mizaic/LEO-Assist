"""One-off encounter rerun using the worker event-handler path."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from libs.keyvault.loader import load_keyvault_secrets
from libs.message_bus.base import Message
from libs.workflow.engine import WorkflowEngine
from libs.workflow.events import ServiceBusEventHandler

PATIENT_ID = "4181221113"
ENCOUNTER_ID = "643b423a-bd67-4a1f-9b00-5337ca45b6dd"
PLAN_DEFINITION_ID = "pd-gp-encounter-coding"


def _print_step(event: dict[str, Any]) -> None:
    if event.get("type") != "step_completed":
        return
    action = str(event.get("action_id") or "")
    output = event.get("output") if isinstance(event.get("output"), dict) else {}
    entities = output.get("entities", []) if isinstance(output, dict) else []
    print(f"[{action}] entities={len(entities)}")
    for entity in entities:
        text = str(entity.get("text", ""))[:70]
        assertion = str(entity.get("assertion", ""))
        tier = str(entity.get("_tier", entity.get("decision_tier", "")))
        reason = str(entity.get("_tier_reason", entity.get("reason", "")))
        guard = str(entity.get("_assertion_guard", ""))
        src = str(entity.get("_llm_check_source", ""))
        print(
            f"  -> {text} | assertion={assertion} | tier={tier} | "
            f"reason={reason} | guard={guard} | src={src}"
        )
    errors = output.get("errors", []) if isinstance(output, dict) else []
    if errors:
        print(f"  errors={errors}")
    if isinstance(output, dict) and "training_labels_written" in output:
        print(f"  training_labels_written={output['training_labels_written']}")


async def main() -> None:
    load_dotenv(ROOT / ".env")
    load_keyvault_secrets()
    os.environ["CODING_MODEL_PROVIDER_ENABLED"] = "true"

    engine = WorkflowEngine()
    handler = ServiceBusEventHandler(engine)

    body = {
        "event_type": "encounter-created",
        "patient_id": PATIENT_ID,
        "encounter_id": ENCOUNTER_ID,
        "plan_definition_id": PLAN_DEFINITION_ID,
        "context": {
            "dry_run": False,
            "mode": "extract_encounter",
            "encounter_id": ENCOUNTER_ID,
            "reset": True,
        },
    }
    message = Message(
        body=body,
        correlation_id=f"manual-rerun-{PATIENT_ID}-{ENCOUNTER_ID}",
        subject="encounter-created",
    )
    result = await handler.handle_message(message, step_callback=_print_step)
    print("\nFinal result keys:", sorted(result.keys()))
    if "errors" in result and result["errors"]:
        print("Final errors:", result["errors"])


if __name__ == "__main__":
    asyncio.run(main())
