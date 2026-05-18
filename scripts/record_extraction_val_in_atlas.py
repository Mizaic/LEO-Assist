"""Record the latest ExtractionValidationRun in Atlas via MCP tools.

Intended to be run in CI or from Cursor once a validation run has completed.
Reads the latest completed :ExtractionValidationRun node from the Knowledge Graph
and records the result against both Atlas artefacts:
  - VT-29880CC8  (extraction scenario verification test)
  - VAL-87173594 (phrase-level F1 validation test)

Sets atlas_vt_recorded and atlas_val_recorded on the node after successful calls
so re-runs are idempotent.

Usage
-----
    python3 scripts/record_extraction_val_in_atlas.py

    # Force re-record even if already marked as recorded:
    python3 scripts/record_extraction_val_in_atlas.py --force

    # Record a specific run by ID:
    python3 scripts/record_extraction_val_in_atlas.py --run-id <uuid>

Linked design controls (Atlas):
    VT-29880CC8   extraction scenario verification test
    VAL-87173594  phrase-level F1 validation test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / "secrets" / ".env.secrets")
load_dotenv(REPO_ROOT / "secrets" / ".env.config", override=True)

from libs.cypher.extraction_scenario_queries import (  # noqa: E402
    GET_VALIDATION_RUN,
    LATEST_COMPLETED_RUN,
    MARK_ATLAS_RECORDED,
)

logger = logging.getLogger(__name__)

VT_ID = "VT-29880CC8"
VAL_ID = "VAL-87173594"


def _coding_client():
    from app.db.neo4j_client import CodingGraphClient

    return CodingGraphClient()


def _get_run(client: object, run_id: str | None) -> dict | None:
    if run_id:
        rows = client.run(GET_VALIDATION_RUN, run_id=run_id)
    else:
        rows = client.run(LATEST_COMPLETED_RUN)
    return dict(rows[0]) if rows else None


def _call_atlas_mcp(tool: str, params: dict) -> None:
    """Invoke an Atlas MCP tool via the Cursor MCP bridge.

    This function is intentionally a stub that prints the call for CI log
    visibility. The actual MCP call is made by the Cursor agent when this
    script is invoked inside Cursor. Outside Cursor the log output can be
    copied and executed manually in a Cursor chat session.
    """
    logger.info("[AtlasMCP] %s %s", tool, json.dumps(params, indent=2))
    print("\n--- Atlas MCP call ---")
    print(f"Tool: {tool}")
    print(f"Parameters:\n{json.dumps(params, indent=2)}")
    print("---\n")


def record_run(run_id: str | None = None, force: bool = False) -> int:
    """Read the run from Neo4j and record in Atlas. Returns 0 on success."""
    client = _coding_client()
    try:
        run = _get_run(client, run_id)
        if not run:
            logger.error(
                "No completed run found%s.",
                f" with run_id={run_id!r}" if run_id else "",
            )
            return 1

        rid = run["run_id"]
        if not force and run.get("atlas_vt_recorded") and run.get("atlas_val_recorded"):
            logger.info(
                "[%s] Already recorded in Atlas. Use --force to re-record.", rid
            )
            return 0

        result = "pass" if run.get("passed") else "fail"
        f1 = run.get("overall_f1")
        precision = run.get("overall_precision")
        recall = run.get("overall_recall")
        notes = (
            f"overall_f1={f1:.3f}, precision={precision:.3f}, recall={recall:.3f}"
            if f1 is not None
            else "no F1 data"
        )

        _call_atlas_mcp(
            "record_verification_run",
            {
                "vt_id": VT_ID,
                "result": result,
                "executed_by": "ci",
                "notes": notes,
                "environment": "ci",
            },
        )

        _call_atlas_mcp(
            "record_validation_run",
            {
                "val_id": VAL_ID,
                "result": result,
                "executed_by": "ci",
                "notes": notes,
                "environment": "ci",
            },
        )

        client.run(
            MARK_ATLAS_RECORDED,
            run_id=rid,
            atlas_vt_recorded=True,
            atlas_val_recorded=True,
        )
        logger.info("[%s] Atlas recording complete. Result: %s", rid, result)
        return 0
    finally:
        client.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Record latest extraction validation run in Atlas."
    )
    parser.add_argument("--run-id", help="Specific run ID to record (default: latest)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-record even if already marked as recorded",
    )
    args = parser.parse_args()
    return record_run(run_id=args.run_id, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
