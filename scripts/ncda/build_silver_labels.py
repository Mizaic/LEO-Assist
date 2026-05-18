#!/usr/bin/env python3
"""Stage 3 - Build silver labels for the broader patient corpus.

Pulls every encounter for the cancer-cohort patient list and labels each one
with predicted NCDA role + outcome + confidence + rationale + supporting
quote. Writes parquet (preferred) or jsonl (fallback) to
artifacts/ncda_silver/<run_id>/labels.<ext>.

LLM-at-curation only - the labelling callable is wired by the operator at
runtime; v0 ships with a deterministic Read-code + phrase pattern fallback
so the rest of the pipeline can train end-to-end without an LLM call.

Usage:
    python scripts/ncda/build_silver_labels.py
    python scripts/ncda/build_silver_labels.py --patients 6309359401 4505618269
    python scripts/ncda/build_silver_labels.py --use-llm
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from neo4j import GraphDatabase  # noqa: E402

from services.analysis_worker.app.ncda_detector.silver_labeller import (  # noqa: E402
    label_corpus,
    labels_to_dicts,
)

_PULL_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE ($patients IS NULL OR coalesce(toString(p.id), toString(p.patient_id)) IN $patients)
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    enc.id AS encounter_id,
    toString(enc.date) AS encounter_date,
    enc.text AS text,
    enc.flags AS flags
ORDER BY patient_id, encounter_date
"""


def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get(
        "NEO4J_URI", ""
    ).strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get(
        "NEO4J_USER", ""
    ).strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get(
        "NEO4J_PASSWORD", ""
    ).strip()
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


def _persist(rows: list[dict], target_dir: Path) -> Path:
    """Write JSONL by default; parquet when pandas+pyarrow are available."""
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd  # type: ignore[import-untyped]

        df = pd.DataFrame(rows)
        target = target_dir / "labels.parquet"
        df.to_parquet(target, index=False)
        return target
    except ImportError:
        target = target_dir / "labels.jsonl"
        with target.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return target


def _build_llm_callback(model: str | None):
    """Return a callable conforming to LlmRelabelFn, or None.

    v0 ships with no live LLM client wired in. The operator can monkey-patch
    or plug an Azure OpenAI client by editing this function.
    """
    if model is None:
        return None
    raise SystemExit(
        f"--use-llm requested model {model!r} but no LLM client is wired. "
        "Implement _build_llm_callback() to call your Azure OpenAI / vLLM "
        "deployment. See SilverLabeller for the expected response schema."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patients", nargs="+", default=None, help="Restrict to these patient ids."
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM-at-curation model (default deterministic).",
    )
    parser.add_argument("--model", default=os.environ.get("NCDA_LLM_MODEL"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = ROOT / "artifacts" / "ncda_silver" / run_id

    driver = _connect()
    try:
        with driver.session() as session:
            rows = [
                dict(r)
                for r in session.run(_PULL_QUERY, patients=args.patients)
            ]
    finally:
        driver.close()

    llm = _build_llm_callback(args.model) if args.use_llm else None
    labels = label_corpus(rows, llm=llm)
    out_path = _persist(labels_to_dicts(labels), target_dir)

    print(f"Silver labels written: {out_path}")
    print(f"Rows: {len(labels)}")
    by_role: dict[str, int] = {}
    for label in labels:
        by_role[label.role] = by_role.get(label.role, 0) + 1
    for role, n in sorted(by_role.items(), key=lambda kv: -kv[1]):
        print(f"  {role}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
