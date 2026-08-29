"""Read-only dump: letter text plus the facts one pipeline run wrote.

For each referral, writes two files into the output directory:
  <referral>.text.txt   raw chunk text as stored on :Chunk
  <referral>.facts.txt  every :DOCUMENTS link stamped with the given run_id

Makes no writes and calls no LLM.

Usage:
    .venv/bin/python scripts/investigations/dump_run_facts.py \
        --out /tmp/leo-five/facts \
        --pair 000481914514=455cca102c8b448f83cf5cc1dc81fbd2
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

_CHUNKS = """
MATCH (rr:ReferralRequest {id: $referral_id})
      -[:HAS_DOCUMENT|HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference)
      -[:HAS_CHUNK]->(c:Chunk)
RETURN c.id AS chunk_id, c.index AS idx, c.text AS text
ORDER BY coalesce(c.index, 0), c.id
"""

_FACTS = """
MATCH (rr:ReferralRequest {id: $referral_id})
      -[:HAS_DOCUMENT|HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference)
      -[:HAS_CHUNK]->(c:Chunk)-[r:DOCUMENTS]->(s)
WHERE r.run_id = $run_id
RETURN c.id AS chunk_id, c.index AS idx,
       r.conceptId AS concept_id, s.name AS concept_name,
       labels(s) AS concept_labels, s.semanticTag AS semantic_tag,
       r.context AS context, r.evidence AS evidence,
       r.evidence_sentence AS evidence_sentence,
       r.confidence AS confidence, r.decision_tier AS decision_tier,
       r.value AS value, r.unit AS unit,
       r.body_site_term AS body_site, r.source AS source
ORDER BY coalesce(c.index, 0), s.name
"""

_ENCOUNTER_FACTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.run_id = $run_id
RETURN e.id AS chunk_id, -1 AS idx,
       r.conceptId AS concept_id, s.name AS concept_name,
       labels(s) AS concept_labels, s.semanticTag AS semantic_tag,
       r.context AS context, r.evidence AS evidence,
       r.evidence_sentence AS evidence_sentence,
       r.confidence AS confidence, r.decision_tier AS decision_tier,
       r.value AS value, r.unit AS unit,
       r.body_site_term AS body_site, r.source AS source
ORDER BY s.name
"""


def _fmt_fact(row: dict) -> str:
    ctx = row.get("context") or {}
    assertion = ctx.get("assertion") if isinstance(ctx, dict) else ctx
    parts = [
        f"chunk {row.get('idx')}",
        f"{row.get('concept_id')}",
        f"{row.get('concept_name')!r}",
        f"tag={row.get('semantic_tag')}",
        f"assertion={assertion}",
    ]
    if row.get("value") is not None:
        parts.append(f"value={row.get('value')} {row.get('unit') or ''}".strip())
    if row.get("body_site"):
        parts.append(f"site={row.get('body_site')}")
    if row.get("decision_tier"):
        parts.append(f"tier={row.get('decision_tier')}")
    if row.get("confidence") is not None:
        parts.append(f"conf={row.get('confidence')}")
    head = "  |  ".join(parts)
    ev = row.get("evidence_sentence") or row.get("evidence") or ""
    return f"{head}\n      evidence: {str(ev)[:300]!r}"


def _dump_one(
    client: PatientGraphClient,
    referral_id: str,
    run_id: str,
    out_dir: pathlib.Path,
) -> None:
    chunks = client.run(_CHUNKS, referral_id=referral_id)
    text_lines = [f"referral {referral_id}  chunks={len(chunks)}", ""]
    for row in chunks:
        text_lines.append(f"----- chunk {row.get('idx')} ({row.get('chunk_id')}) -----")
        text_lines.append(str(row.get("text") or ""))
        text_lines.append("")
    (out_dir / f"{referral_id}.text.txt").write_text("\n".join(text_lines))

    facts = list(client.run(_FACTS, referral_id=referral_id, run_id=run_id))
    facts += list(client.run(_ENCOUNTER_FACTS, run_id=run_id))
    fact_lines = [
        f"referral {referral_id}  run {run_id}  facts={len(facts)}",
        "",
    ]
    for row in facts:
        fact_lines.append(_fmt_fact(dict(row)))
    (out_dir / f"{referral_id}.facts.txt").write_text("\n".join(fact_lines))
    print(f"{referral_id}: {len(chunks)} chunks, {len(facts)} facts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        help="referral_id=run_id",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = PatientGraphClient()
    try:
        for pair in args.pair:
            referral_id, _, run_id = pair.partition("=")
            _dump_one(client, referral_id.strip(), run_id.strip(), out_dir)
    finally:
        client.close()


if __name__ == "__main__":
    main()
