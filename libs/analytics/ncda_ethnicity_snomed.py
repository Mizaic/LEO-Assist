"""NCDA ethnicity benchmark keys and SNOMED CT concept IDs.

Loads ``configs/snomed/snomed_ncda_ethnicity_mapping.json`` (same source as the
terminology ValueSet ``ncda-ethnicity`` seed). Used by audit demographics to
aggregate distinct patients per coded ethnicity concept for radar charts.

Atlas trace:
  DO: DO-4DADBA3F
  DI: DI-87D92943
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_PATH = _REPO_ROOT / "configs" / "snomed" / "snomed_ncda_ethnicity_mapping.json"


@lru_cache(maxsize=1)
def load_ncda_ethnicity_snomed_ids() -> tuple[str, ...]:
    """Return sorted unique SNOMED concept ids (strings) from the NCDA mapping file."""
    data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    out: set[str] = set()
    for _label, meta in (data.get("mappings") or {}).items():
        cid = meta.get("concept_id")
        if cid is not None:
            out.add(str(cid))
    return tuple(sorted(out))


@lru_cache(maxsize=1)
def load_ncda_ethnicity_benchmark_table() -> tuple[dict[str, object], ...]:
    """Rows keyed by SNOMED id string: benchmark_key, preferred_term."""
    data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for benchmark_key, meta in (data.get("mappings") or {}).items():
        cid = meta.get("concept_id")
        if cid is None:
            continue
        rows.append(
            {
                "snomed": str(cid),
                "benchmark_key": benchmark_key,
                "preferred_term": meta.get("preferred_term") or benchmark_key,
            }
        )
    rows.sort(key=lambda r: str(r["snomed"]))
    return tuple(rows)
