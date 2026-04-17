"""Invoke the four UI quality endpoints directly (bypassing HTTP auth).

Used to capture before/after snapshots around lab-triple backfill. Calls the
same Python functions the FastAPI handlers call, so the output is byte-for-
byte what the UI sees (minus the HTTP envelope).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Add services/api so the router's `from app.*` imports resolve.
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.pipeline.label_filter import (  # noqa: E402
    compute_export_diagnostics,
    compute_lab_triple_diagnostics,
)
from services.api.app.routers.training import (  # noqa: E402
    _ENTITY_STORED_TO_DISPLAY,
    _extract_phrase_conflicts,
    _load_phrase_multilabel_policy,
)


def _label_distribution(client: KnowledgeGraphClient) -> dict[str, Any]:
    counter: Counter = Counter()
    total_records = 0
    with client.session() as session:
        rows = session.run(
            """
            MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
            WHERE c.status = 'completed'
              AND g.entities_json IS NOT NULL
            RETURN g.entities_json AS entities_json
            """
        )
        for row in rows:
            total_records += 1
            entities = json.loads(row["entities_json"] or "[]")
            for ent in entities:
                raw = str(
                    ent.get("label") or ent.get("semantic_tag") or "UNKNOWN"
                ).lower()
                label = _ENTITY_STORED_TO_DISPLAY.get(raw, raw.upper())
                counter[label] += 1
    return {
        "total_records": total_records,
        "total_entities": sum(counter.values()),
        "distribution": [
            {"label": lbl, "count": cnt}
            for lbl, cnt in counter.most_common()
        ],
    }


def _phrase_consistency(client: KnowledgeGraphClient) -> dict[str, Any]:
    with client.session() as session:
        policy, policy_rows = _load_phrase_multilabel_policy(session)
        rows = [
            dict(r)
            for r in session.run(
                """
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed'
                  AND g.entities_json IS NOT NULL
                RETURN
                  g.label_id AS label_id,
                  g.text AS text,
                  g.entities_json AS entities_json,
                  g.source AS source
                ORDER BY g.updated_at DESC
                """
            )
        ]
    return _extract_phrase_conflicts(
        rows,
        phrase_filter=None,
        min_occurrences=2,
        max_examples=5,
        top=10,
        policy=policy,
        policy_rows=policy_rows,
    )


def snapshot() -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        label_dist = _label_distribution(client)
        phrase = _phrase_consistency(client)
    finally:
        client.close()

    export_diag = compute_export_diagnostics()
    lab_diag = compute_lab_triple_diagnostics()

    return {
        "label_distribution": {
            "total_records": label_dist["total_records"],
            "total_entities": label_dist["total_entities"],
            "distribution": label_dist["distribution"],
        },
        "export_diagnostics": {
            "keys": sorted(export_diag.keys()),
            "assertion_filtered_count": len(
                export_diag.get("assertion_filtered") or []
            ),
            "span_misaligned_count": len(
                export_diag.get("span_misaligned") or []
            ),
        },
        "phrase_consistency": {
            "total_phrases_examined": phrase.get("total_phrases_examined"),
            "multi_label_phrases": phrase.get("multi_label_phrases"),
            "approved_phrases": phrase.get("approved_phrases"),
            "conflict_count": len(phrase.get("conflicts") or []),
            "top_conflict_phrases": [
                c.get("phrase") for c in (phrase.get("conflicts") or [])[:5]
            ],
        },
        "lab_triple_diagnostics": {
            "total_lab_records": lab_diag.get("total_lab_records"),
            "complete": lab_diag.get("complete"),
            "incomplete": (
                int(lab_diag.get("total_lab_records") or 0)
                - int(lab_diag.get("complete") or 0)
            ),
            "missing_procedure": lab_diag.get("missing_procedure"),
            "missing_observable": lab_diag.get("missing_observable"),
            "missing_finding": lab_diag.get("missing_finding"),
            "sample_record_ids": [
                r.get("label_id")
                for r in (lab_diag.get("missing_records") or [])[:10]
            ],
        },
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
