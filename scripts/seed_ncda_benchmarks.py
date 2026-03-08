"""Seed NCDA 2018 benchmarks into the Knowledge Graph.

Reads external_content/ncda_2018_benchmarks.json and loads it as BenchmarkSet
+ BenchmarkValue nodes.

Usage:
    python scripts/seed_ncda_benchmarks.py

Only seeds when no BenchmarkSet for this audit exists; skips if already present
to avoid overwriting user-modified benchmarks.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fhir_api.app.services.benchmark_loader import flatten_benchmarks
from services.fhir_api.app.services import benchmark_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_BENCHMARKS_JSON = Path(__file__).resolve().parents[1] / "external_content" / "ncda_2018_benchmarks.json"


def main() -> int:
    if not _BENCHMARKS_JSON.exists():
        logger.error("Benchmarks file not found: %s", _BENCHMARKS_JSON)
        return 1

    data = json.loads(_BENCHMARKS_JSON.read_text(encoding="utf-8"))
    values = flatten_benchmarks(data, template_id="ncda")
    if not values:
        logger.warning("No benchmark data extracted from %s", _BENCHMARKS_JSON.name)
        return 0

    audit_id = values[0].get("audit_id", "ncda-2018")
    audit_meta = data.get("audit", {})

    if benchmark_service.get_benchmark_set(audit_id):
        logger.info("Skipped — BenchmarkSet %s already present.", audit_id)
        return 0

    benchmark_service.create_benchmark_set({
        "id": audit_id,
        "name": audit_meta.get("name", "NCDA 2018"),
        "source": "uploaded",
        "audit_year": audit_meta.get("year"),
        "metadata": audit_meta,
    })

    deleted = benchmark_service.delete_benchmark_values_by_metric_ids(
        audit_id, ["demographics.sex.male", "demographics.sex.female"]
    )
    if deleted:
        logger.info("Deleted %d old sex benchmarks (male/female split)", deleted)

    count = benchmark_service.upsert_benchmark_values(audit_id, values)
    logger.info("Seeded %d BenchmarkValue nodes for %s", count, audit_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
