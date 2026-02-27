"""Create Azure Service Bus queues required by the coding/analysis workers.

Usage:
    python scripts/setup_service_bus.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from azure.servicebus.management import ServiceBusAdministrationClient

QUEUES = [
    "coding-jobs",
    "analysis-jobs",
]


def main():
    conn_str = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
    admin = ServiceBusAdministrationClient.from_connection_string(conn_str)

    existing = {q.name for q in admin.list_queues()}
    print(f"Existing queues: {existing or '(none)'}")

    for queue_name in QUEUES:
        if queue_name in existing:
            print(f"  [ok]  Queue '{queue_name}' already exists")
        else:
            admin.create_queue(queue_name)
            print(f"  [new] Queue '{queue_name}' created")

    print("\nDone. Queues ready for coding and analysis workers.")


if __name__ == "__main__":
    main()
