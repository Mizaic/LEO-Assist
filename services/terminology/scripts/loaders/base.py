"""
Shared infrastructure for all terminology loaders.

Provides streaming file readers, batched Neo4j writes, and progress logging.
"""

from __future__ import annotations

import csv
import logging
import sys
import time
from pathlib import Path
from typing import Generator

from neo4j import AsyncDriver, AsyncSession

logger = logging.getLogger(__name__)

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

BATCH_SIZE = 5_000


def stream_rf2(
    filepath: Path,
) -> Generator[dict[str, str], None, None]:
    """Stream an RF2 file (tab-delimited with header row) as dicts."""
    with open(filepath, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


def stream_rrf(
    filepath: Path,
    columns: list[str],
) -> Generator[dict[str, str], None, None]:
    """Stream an RRF file (pipe-delimited, no header) as dicts."""
    col_count = len(columns)
    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            fields = line.rstrip("\n").split("|")
            if len(fields) >= col_count:
                yield dict(zip(columns, fields[:col_count]))


def normalize_term(term: str) -> str:
    """Lowercase and strip semantic tags like (disorder) for matching."""
    t = term.strip().lower()
    if t.endswith(")"):
        paren = t.rfind("(")
        if paren > 0:
            t = t[:paren].strip()
    return t


class BatchWriter:
    """Accumulates rows and flushes to Neo4j in batches."""

    def __init__(
        self,
        session: AsyncSession,
        cypher: str,
        batch_size: int = BATCH_SIZE,
        label: str = "",
        extra_params: dict | None = None,
    ):
        self._session = session
        self._cypher = cypher
        self._batch_size = batch_size
        self._label = label
        self._extra = extra_params or {}
        self._buffer: list[dict] = []
        self._total = 0
        self._start = time.monotonic()

    async def add(self, row: dict) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self._batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        count = len(self._buffer)
        rows = self._buffer
        extra = self._extra
        self._buffer = []

        async def _tx(tx):
            await tx.run(self._cypher, rows=rows, **extra)

        await self._session.execute_write(_tx)
        self._total += count
        elapsed = time.monotonic() - self._start
        rate = self._total / elapsed if elapsed > 0 else 0
        logger.info(
            "%s: %d rows (%.0f/s)", self._label, self._total, rate
        )

    async def finish(self) -> int:
        await self.flush()
        elapsed = time.monotonic() - self._start
        logger.info(
            "%s: complete — %d rows in %.1fs",
            self._label,
            self._total,
            elapsed,
        )
        return self._total
