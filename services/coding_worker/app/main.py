"""Coding Worker service.

Consumes coding-job messages from the message bus, runs the two-phase
coding pipeline (LLM extract -> Terminology API resolve), and streams
progress to Redis for the Core API to relay via SSE.
"""

from __future__ import annotations

import asyncio
import logging
import os

from libs.message_bus.factory import create_message_bus
from libs.message_bus.base import Message
from libs.utils.logging import configure_logging
from services.coding_worker.app.services.job_handler import handle_coding_job

configure_logging(service_name="coding-worker")

# Suppress noisy Azure SDK internals — we only care about errors
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

logger = logging.getLogger("coding-worker")

QUEUE_NAME = os.getenv("CODING_QUEUE_NAME", "coding-jobs")


async def main():
    logger.info("Coding Worker starting — listening on queue: %s", QUEUE_NAME)
    bus = create_message_bus()

    async def on_message(msg: Message):
        await handle_coding_job(msg)

    await bus.subscribe(QUEUE_NAME, on_message)
    logger.info("Coding Worker subscribed. Waiting for messages...")

    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Coding Worker shutting down")
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
