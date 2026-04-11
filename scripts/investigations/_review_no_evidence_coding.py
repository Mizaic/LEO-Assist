"""Review all 'No evidence of cancer found' (395100000) coded encounters.

Shows the evidence text, assertion, confidence, source, and whether the
encounter sits in a fast-track patient cohort. Flags any suspicious codings
(e.g. wrong assertion, low confidence, evidence text that doesn't look right).

Run:
    python scripts/investigations/_review_no_evidence_coding.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

CONCEPT_ID = 395100000
CONCEPT_NAME = "No evidence of cancer found (situation)"

_Q_ALL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE c.conceptId = $cid
RETURN
    toString(p.id)                   AS patient_id,
    toString(e.id)                   AS encounter_id,
    coalesce(toString(e.date), '')   AS enc_date,
    coalesce(e.text, e.note, e.description, '') AS enc_text,
    r.evidence_sentence              AS evidence_sentence,
    r.evidence                       AS evidence,
    r.confidence                     AS confidence,
    r.context                        AS context,
    r.source                         AS source,
    r.model_name                     AS model_name,
    r.decision_tier                  AS decision_tier,
    r.audit_flag                     AS audit_flag
ORDER BY p.id, e.date
"""


def _parse_assertion(context_str) -> str:
    if not context_str:
        return "unknown"
    try:
        ctx = json.loads(context_str)
        return ctx.get("assertion", "unknown")
    except Exception:
        return str(context_str)[:40]


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    print(f"Reviewing all DOCUMENTS codings for: {CONCEPT_ID} | {CONCEPT_NAME}")
    print("=" * 80)

    rows = []
    with client.session() as session:
        rows = list(session.run(_Q_ALL, cid=CONCEPT_ID))
    client.close()

    print(f"Total coded encounters: {len(rows)}")
    print()

    suspicious = []
    by_source: dict[str, int] = {}
    by_assertion: dict[str, int] = {}

    for i, r in enumerate(rows, 1):
        assertion = _parse_assertion(r["context"])
        confidence = r["confidence"] or 0.0
        source = r["source"] or "unknown"
        evidence = (r["evidence_sentence"] or r["evidence"] or "").strip()
        enc_text = (r["enc_text"] or "")[:200]
        model = r["model_name"] or "unknown"
        tier = r["decision_tier"] or "unknown"

        by_source[source] = by_source.get(source, 0) + 1
        by_assertion[assertion] = by_assertion.get(assertion, 0) + 1

        # Flag if assertion is NOT 'present' (this is a situation, should always be present)
        # or confidence is suspiciously low
        is_suspicious = assertion != "present" or confidence < 0.5

        if is_suspicious:
            suspicious.append(r)

        flag = "!! SUSPICIOUS" if is_suspicious else ""
        print(
            f"[{i:2d}] Patient {r['patient_id']}  enc={r['encounter_id'][:8]}...  date={r['enc_date'][:10]}  {flag}"
        )
        print(
            f"     assertion  : {assertion}  |  confidence={confidence:.2f}  |  source={source}  |  model={model}"
        )
        print(f"     evidence   : {evidence[:100] or '(none)'}")
        if enc_text and enc_text.strip() != evidence.strip():
            # Show a snippet of the encounter text for context
            snippet = enc_text.replace("\n", " ")[:120]
            print(f"     enc_text   : {snippet}")
        print()

    print("=" * 80)
    print("Summary")
    print(f"  Total codings        : {len(rows)}")
    print(f"  Suspicious (non-present assertion or low confidence): {len(suspicious)}")
    print()
    print("  By source:")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {cnt:3d}  {src}")
    print()
    print("  By assertion:")
    for asn, cnt in sorted(by_assertion.items(), key=lambda x: -x[1]):
        print(f"    {cnt:3d}  {asn}")

    if suspicious:
        print()
        print("  Suspicious encounters to investigate:")
        for r in suspicious:
            assertion = _parse_assertion(r["context"])
            print(
                f"    enc={r['encounter_id']}  assertion={assertion}  conf={r['confidence']}"
            )


if __name__ == "__main__":
    main()
