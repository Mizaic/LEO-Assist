"""Publish pipeline-jobs messages for all demo patient encounters.

Publishes to the Azure Service Bus 'pipeline-jobs' queue so the running
pipeline worker processes them with the real LLM pipeline.

Usage:
    python scripts/trigger_demo_pipeline.py                # all 195 encounters
    python scripts/trigger_demo_pipeline.py --referrals-only
    python scripts/trigger_demo_pipeline.py --encounters-only
    python scripts/trigger_demo_pipeline.py --dry-run
    python scripts/trigger_demo_pipeline.py --patient demo-patient-001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import os

QUEUE_NAME = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
REFERRAL_PLAN = "pd-referral-assessment"
ENCOUNTER_PLAN = "pd-gp-encounter-coding"


def _build_messages(
    *,
    referrals: bool,
    encounters: bool,
    patient_filter: str | None,
) -> list[dict]:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    msgs: list[dict] = []
    try:
        if referrals:
            rows = client.run(
                """
                MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
                WHERE p.id STARTS WITH 'demo-patient-0'
                AND e.id CONTAINS 'referral'
                AND ($patient IS NULL OR p.id = $patient)
                RETURN p.id AS patient_id, e.id AS encounter_id
                ORDER BY p.id
                """,
                patient=patient_filter,
            )
            for r in rows:
                msgs.append(
                    {
                        "event_type": "referral-received",
                        "plan_definition_id": REFERRAL_PLAN,
                        "patient_id": r["patient_id"],
                        "encounter_id": r["encounter_id"],
                        "run_id": str(uuid.uuid4()),
                    }
                )

        if encounters:
            rows = client.run(
                """
                MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
                WHERE p.id STARTS WITH 'demo-patient-0'
                AND NOT e.id CONTAINS 'referral'
                AND ($patient IS NULL OR p.id = $patient)
                RETURN p.id AS patient_id, e.id AS encounter_id
                ORDER BY p.id, e.id
                """,
                patient=patient_filter,
            )
            for r in rows:
                msgs.append(
                    {
                        "event_type": "encounter-created",
                        "plan_definition_id": ENCOUNTER_PLAN,
                        "patient_id": r["patient_id"],
                        "encounter_id": r["encounter_id"],
                        "run_id": str(uuid.uuid4()),
                    }
                )
    finally:
        client.close()
    return msgs


async def _publish_via_service_bus(messages: list[dict], dry_run: bool) -> None:
    conn_str = os.environ.get("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
    if not conn_str:
        print("ERROR: AZURE_SERVICE_BUS_CONNECTION_STRING is not set.")
        sys.exit(1)

    from azure.servicebus.aio import ServiceBusClient
    from azure.servicebus import ServiceBusMessage

    if dry_run:
        print(f"[dry-run] Would publish {len(messages)} messages to {QUEUE_NAME}")
        for m in messages[:5]:
            print(f"  {m['event_type']} | {m['patient_id']} | {m['encounter_id']}")
        if len(messages) > 5:
            print(f"  ... and {len(messages) - 5} more")
        return

    async with ServiceBusClient.from_connection_string(conn_str) as sbc:
        sender = sbc.get_queue_sender(queue_name=QUEUE_NAME)
        async with sender:
            batch_size = 50
            for i in range(0, len(messages), batch_size):
                chunk = messages[i : i + batch_size]
                sb_msgs = [
                    ServiceBusMessage(
                        body=json.dumps(m),
                        content_type="application/json",
                        correlation_id=m["run_id"],
                    )
                    for m in chunk
                ]
                await sender.send_messages(sb_msgs)
                print(
                    f"  Published batch {i // batch_size + 1}"
                    f" ({i + len(chunk)}/{len(messages)})"
                )

    print(f"\nDone. {len(messages)} messages published to '{QUEUE_NAME}'.")
    print("The running pipeline worker will process them.")
    print("Monitor progress: curl http://localhost:8006/health/consumer")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trigger demo pipeline runs via Service Bus")
    p.add_argument("--referrals-only", action="store_true")
    p.add_argument("--encounters-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--patient", help="Limit to one patient ID")
    return p.parse_args()


async def main() -> None:
    args = _parse_args()
    do_referrals = not args.encounters_only
    do_encounters = not args.referrals_only

    msgs = _build_messages(
        referrals=do_referrals,
        encounters=do_encounters,
        patient_filter=args.patient,
    )

    ref_count = sum(1 for m in msgs if m["event_type"] == "referral-received")
    enc_count = sum(1 for m in msgs if m["event_type"] == "encounter-created")
    print(f"Messages to publish: {ref_count} referrals + {enc_count} encounters")

    await _publish_via_service_bus(msgs, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
