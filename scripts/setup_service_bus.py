"""Create / update Azure Service Bus queues for pipeline and analysis workers.

Queue settings:
  - lock_duration: 5 minutes (maximum on Standard tier).
    AutoLockRenewer in the adapter renews this every ~4.5 min for the full job duration.
  - max_delivery_count: 3 — a patient job that fails 3 times goes to dead-letter
    rather than retrying forever.
  - default_message_time_to_live: 1 day — stale unprocessed jobs are discarded.
  - dead_lettering_on_message_expiration: True — expired messages are inspectable.

Usage:
    python scripts/setup_service_bus.py
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from azure.servicebus.management import ServiceBusAdministrationClient, QueueProperties

QUEUES = [
    "pipeline-jobs",
    "analysis-jobs",
    # Dedicated queue for weekly audit jobs (CTO-002 fix: queue isolation).
    # Audit runs are long-running and must never delay real-time pipeline jobs.
    "audit-jobs",
]

QUEUE_SETTINGS = dict(
    lock_duration=timedelta(minutes=5),           # Max on Standard tier; AutoLockRenewer extends beyond this
    max_delivery_count=3,                          # Dead-letter after 3 failures
    default_message_time_to_live=timedelta(days=1),
    dead_lettering_on_message_expiration=True,
    enable_batched_operations=True,
)


def _apply_settings(props: QueueProperties) -> bool:
    """Update props in place. Returns True if any field changed."""
    changed = False
    for key, value in QUEUE_SETTINGS.items():
        if getattr(props, key, None) != value:
            setattr(props, key, value)
            changed = True
    return changed


def main():
    conn_str = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
    admin = ServiceBusAdministrationClient.from_connection_string(conn_str)

    existing = {q.name: q for q in admin.list_queues()}
    print(f"Existing queues: {set(existing) or '(none)'}\n")

    for queue_name in QUEUES:
        if queue_name in existing:
            props = admin.get_queue(queue_name)
            changed = _apply_settings(props)
            if changed:
                admin.update_queue(props)
                print(f"  [updated] Queue '{queue_name}' — settings applied")
            else:
                print(f"  [ok]     Queue '{queue_name}' — settings already correct")
        else:
            admin.create_queue(queue_name, **QUEUE_SETTINGS)
            print(f"  [new]    Queue '{queue_name}' created with production settings")

    print("\nQueue settings summary:")
    print(f"  lock_duration          : 5 minutes (AutoLockRenewer extends for full job)")
    print(f"  max_delivery_count     : 3 (dead-letter after 3 failures)")
    print(f"  message_ttl            : 1 day")
    print(f"  dead_letter_on_expiry  : yes")
    print("\nDone.")


if __name__ == "__main__":
    main()
