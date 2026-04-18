"""VT-LEO-AI-218: SNOMED -> OPCS-4 simple-map loader.

Covers DI-LEO-AI-226, DO-LEO-AI-223 (snomed_map.py extension).

Verifies:
  - load_opcs4_map filters strictly on OPCS4_REFSET_ID (no leakage from
    CTV3 / ICD-O / other refsets that share the SimpleMap file)
  - load_simple_map with refset_filter=CTV3_REFSET_ID skips OPCS-4 rows
    so OPCS-4 codes never get loaded as ReadCodes (regression guard)
  - Inactive rows are skipped
  - Rows with empty mapTarget are skipped
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.terminology.scripts.loaders import snomed_map as mod
from services.terminology.scripts.loaders.snomed_map import (
    CTV3_REFSET_ID,
    OPCS4_REFSET_ID,
)

HEADER = (
    "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId\tmapTarget\n"
)


def _row(active: str, refset: str, snomed: str, target: str) -> str:
    return (
        f"uuid-x\t20240101\t{active}\t900000000000012004\t"
        f"{refset}\t{snomed}\t{target}\n"
    )


@pytest.fixture
def mixed_simple_map(tmp_path: Path) -> Path:
    p = tmp_path / "der2_sRefset_SimpleMapUKCRSnapshot.txt"
    p.write_text(
        HEADER
        + _row("1", CTV3_REFSET_ID, "84114007", "G58..")
        + _row("1", OPCS4_REFSET_ID, "265456001", "A01.1")
        + _row("1", OPCS4_REFSET_ID, "112700009", "A02.1")
        + _row("1", "999000000000000000", "111111111", "Z99")  # other refset
        + _row("0", OPCS4_REFSET_ID, "222222222", "B01.1")  # inactive
        + _row("1", OPCS4_REFSET_ID, "333333333", ""),  # blank target
        encoding="utf-8",
    )
    return p


class _FakeAsyncSession:
    def __init__(self, store: dict):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute_write(self, fn):
        class _Tx:
            def __init__(self, store):
                self._store = store

            async def run(self, cypher, rows=None, **extra):
                self._store.setdefault("batches", []).append(
                    {"cypher": cypher, "rows": rows}
                )

        await fn(_Tx(self._store))


class _FakeDriver:
    def __init__(self, store: dict):
        self._store = store

    def session(self):
        return _FakeAsyncSession(self._store)


@pytest.mark.asyncio
async def test_load_opcs4_map_filters_strictly(mixed_simple_map):
    store: dict = {}
    driver = _FakeDriver(store)
    total = await mod.load_opcs4_map(driver, mixed_simple_map, batch_size=1000)

    assert total == 2  # only the two active OPCS4-refset rows with non-blank target
    rows_written = [r for batch in store["batches"] for r in batch["rows"]]
    targets = sorted(r["map_target"] for r in rows_written)
    assert targets == ["A01.1", "A02.1"]
    cyphers = {batch["cypher"] for batch in store["batches"]}
    assert any("MAPS_TO_OPCS4" in q for q in cyphers)


@pytest.mark.asyncio
async def test_load_simple_map_ctv3_filter_excludes_opcs4(mixed_simple_map):
    store: dict = {}
    driver = _FakeDriver(store)
    total = await mod.load_simple_map(
        driver,
        mixed_simple_map,
        batch_size=1000,
        refset_filter=CTV3_REFSET_ID,
    )

    assert total == 1  # only the CTV3 row
    rows_written = [r for batch in store["batches"] for r in batch["rows"]]
    targets = [r["map_target"] for r in rows_written]
    assert targets == ["G58.."]
    cyphers = {batch["cypher"] for batch in store["batches"]}
    assert any("MAPS_TO_READ" in q for q in cyphers)
    assert not any("MAPS_TO_OPCS4" in q for q in cyphers)


@pytest.mark.asyncio
async def test_load_simple_map_no_filter_loads_all_active_targets(mixed_simple_map):
    """Belt-and-braces: with no filter, every active row with a target is loaded.

    This is the legacy behaviour and must remain available for callers that
    want to pre-filter via a separate file.
    """
    store: dict = {}
    driver = _FakeDriver(store)
    total = await mod.load_simple_map(driver, mixed_simple_map, batch_size=1000)
    # 1 CTV3 + 2 OPCS4 + 1 other = 4 active rows with non-blank target
    assert total == 4
