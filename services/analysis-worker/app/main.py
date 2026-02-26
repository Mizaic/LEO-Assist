"""Analysis Worker service.

Consumes analysis-job messages from the message bus. Runs:
- Anchor detection (referral / diagnosis / treatment)
- Episode building and consolidation
- CSS / unwarranted variation detection
- Abnormal results analysis
- KPI and quality metric calculation
"""

from __future__ import annotations

import asyncio
import logging
import os

from libs.message_bus.factory import create_message_bus
from libs.message_bus.base import Message
from services.analysis_worker.app.services.job_handler import handle_analysis_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("analysis-worker")

QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis-jobs")


async def main():
    logger.info("Analysis Worker starting — listening on queue: %s", QUEUE_NAME)
    bus = create_message_bus()

    async def on_message(msg: Message):
        await handle_analysis_job(msg)

    await bus.subscribe(QUEUE_NAME, on_message)
    logger.info("Analysis Worker subscribed. Waiting for messages...")

    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Analysis Worker shutting down")
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
