"""Load pre-approved NCDA surface forms from auditor_2 config JSONs into the coding graph.

Reads snomed_ncda_*_mapping.json files, extracts surface-form -> concept_id pairs from
guideline_synonyms and preferred_term, and writes SurfaceForm nodes with MAPS_TO
relationships to the Neo4j coding graph.

Usage:
    python scripts/load_preapproved_surface_forms.py [--config-dir PATH] [--dry-run] [--batch-size 500]
    python scripts/load_preapproved_surface_forms.py --report-missing  # log concept IDs not in graph
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "services" / "api"
if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

from app.db.neo4j_client import CodingGraphClient
from app.services.terminology_writeback_service import UPSERT_SURFACE_FORMS, _normalize

log = logging.getLogger(__name__)

# Default config dir: auditor_2/agent/configs (sibling of Primary-care-audit)
DEFAULT_CONFIG_DIR = ROOT / ".." / "auditor_2" / "agent" / "configs"

EXISTING_CONCEPTS_QUERY = "MATCH (c:Concept) RETURN c.id AS id"


def _parse_ncda_file(path: Path) -> list[tuple[str, int]]:
    """Parse NCDA mapping JSON and yield (surface_form, concept_id) pairs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    mappings = data.get("mappings") or {}
    pairs: list[tuple[str, int]] = []
    for _key, entry in mappings.items():
        concept_id = entry.get("concept_id")
        if concept_id is None:
            continue
        synonyms: set[str] = set(entry.get("guideline_synonyms") or [])
        if entry.get("preferred_term"):
            synonyms.add(entry["preferred_term"])
        for surface_form in synonyms:
            stripped = (surface_form or "").strip()
            if stripped:
                pairs.append((stripped, concept_id))
    return pairs


def extract_rows(config_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Extract writeback rows from all snomed_ncda_*.json files. Returns (rows, stats)."""
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    stats: dict[str, int] = {"files_read": 0, "pairs_extracted": 0, "rows_eligible": 0}

    for path in sorted(config_dir.glob("snomed_ncda_*.json")):
        try:
            pairs = _parse_ncda_file(path)
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Skipping %s: %s", path.name, e)
            continue
        stats["files_read"] += 1
        stats["pairs_extracted"] += len(pairs)

        for form, concept_id in pairs:
            normalized = _normalize(form)
            concept_id_str = str(concept_id)
            key = (normalized, concept_id_str)
            if key in seen:
                continue
            seen.add(key)
            stats["rows_eligible"] += 1
            rows.append({
                "form": form,
                "normalized": normalized,
                "concept_id": concept_id_str,
                "confidence": 1.0,
                "approved_by": "ncda_guideline_loader",
                "source": "ncda_preapproved",
                "status": "approved",
                "provenance": "guideline_config_loader",
            })

    return rows, stats


def fetch_existing_concept_ids(session) -> set[str]:
    """Return set of Concept IDs that exist in the coding graph."""
    result = session.run(EXISTING_CONCEPTS_QUERY)
    return {str(r["id"]) for r in result if r["id"] is not None}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR.resolve(),
        help="Directory containing snomed_ncda_*.json files",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report stats only, no Neo4j writes")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for Neo4j writes")
    parser.add_argument(
        "--report-missing",
        action="store_true",
        help="Log concept IDs and surface forms that were skipped (Concept not in graph)",
    )
    args = parser.parse_args()

    config_dir = args.config_dir.resolve()
    if not config_dir.is_dir():
        log.error("Config dir does not exist: %s", config_dir)
        sys.exit(1)

    rows, extract_stats = extract_rows(config_dir)
    log.info(
        "Extracted: %d files, %d pairs, %d unique rows",
        extract_stats["files_read"],
        extract_stats["pairs_extracted"],
        extract_stats["rows_eligible"],
    )

    if not rows:
        log.info("No rows to write.")
        return

    client = CodingGraphClient()
    try:
        with client.session() as session:
            existing = fetch_existing_concept_ids(session)
            filtered = [r for r in rows if r["concept_id"] in existing]
            missing_rows = [r for r in rows if r["concept_id"] not in existing]
            concepts_not_found = len(missing_rows)

            if concepts_not_found:
                log.warning("%d rows skipped (Concept not in graph)", concepts_not_found)
                if args.report_missing:
                    # Group by concept_id with sample surface forms
                    by_concept: dict[str, list[str]] = defaultdict(list)
                    for r in missing_rows:
                        by_concept[r["concept_id"]].append(r["form"])
                    log.info("Missing concept IDs (not in UK SNOMED graph):")
                    for cid in sorted(by_concept.keys(), key=lambda x: int(x) if x.lstrip("-").isdigit() else 0):
                        forms = by_concept[cid][:5]  # up to 5 examples
                        more = f" ... +{len(by_concept[cid]) - 5} more" if len(by_concept[cid]) > 5 else ""
                        log.info("  %s: %s%s", cid, ", ".join(repr(f) for f in forms), more)

            if args.dry_run:
                log.info("Dry run - no writes performed.")
                return

            written = 0
            for i in range(0, len(filtered), args.batch_size):
                chunk = filtered[i : i + args.batch_size]
                result = session.run(UPSERT_SURFACE_FORMS, rows=chunk)
                rec = result.single()
                batch_written = rec["written"] if rec else len(chunk)
                written += batch_written
                log.info("Wrote %d/%d surface forms...", written, len(filtered))

            log.info(
                "Complete: %d surface forms written, %d concepts not found",
                written,
                concepts_not_found,
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
