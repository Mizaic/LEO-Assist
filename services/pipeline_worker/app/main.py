"""Pipeline Worker service.

Unified worker that replaces coding_worker and analysis_worker.
Consumes pipeline-job messages from the message bus, delegates to the
WorkflowEngine which dispatches LangGraph subgraphs based on FHIR
PlanDefinition/ActivityDefinition configuration.
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

import asyncio
import logging
import os

from libs.message_bus.factory import create_message_bus
from libs.message_bus.base import Message
from libs.utils.logging import configure_logging
from libs.workflow.engine import WorkflowEngine
from libs.workflow.events import ServiceBusEventHandler

configure_logging(service_name="pipeline-worker")

for _ns in (
    "azure.servicebus",
    "azure.servicebus._pyamqp",
    "azure.servicebus._pyamqp.aio",
    "azure.core.pipeline.policies.http_logging_policy",
    "uamqp",
    "httpx",
    "botocore",
    "botocore.credentials",
):
    logging.getLogger(_ns).setLevel(logging.WARNING)

logger = logging.getLogger("pipeline-worker")

QUEUE_NAME = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")


async def main():
    logger.info("Pipeline Worker starting — listening on queue: %s", QUEUE_NAME)
    bus = create_message_bus()

    # Initialize Neo4j driver if available
    neo4j_driver = None
    try:
        from libs.neo4j_client.client import get_async_driver
        neo4j_driver = get_async_driver()
    except Exception:
        logger.warning("Neo4j driver not available — running without graph storage")

    engine = WorkflowEngine(neo4j_driver=neo4j_driver, message_bus=bus)
    handler = ServiceBusEventHandler(engine)

    async def on_message(msg: Message):
        await handler.handle_message(msg.body)

    await bus.subscribe(QUEUE_NAME, on_message)
    logger.info("Pipeline Worker subscribed. Waiting for messages...")

    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Pipeline Worker shutting down")
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
