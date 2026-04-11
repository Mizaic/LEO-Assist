"""Smoke-test the wired LLMExtractor against a single real encounter.

Usage:
    python scripts/investigations/test_llm_extractor.py [encounter_id]

If no encounter_id is supplied, picks the most recently processed encounter
from the audit SQLite DB so we can compare LLM extraction against the audit's
own findings for the same encounter.

Prints:
  - Encounter text (first 400 chars)
  - Existing DOCUMENTS links (what the NER pipeline already coded)
  - LLM-extracted terms (raw, before SNOMED resolution)
  - Side-by-side diff: new vs existing
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

# Load env so Bedrock credentials are available
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient
from libs.nlp.sentence_splitter import SentenceSplitter
from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

AUDIT_DB = (
    ROOT / "scripts" / "investigations" / "encounter_audit" / "encounter_audit.db"
)

_Q_ENCOUNTER = """
MATCH (e:Encounter {id: $eid})
RETURN e.text AS text, e.date AS date
"""

_Q_CODED = """
MATCH (e:Encounter {id: $eid})-[r:DOCUMENTS]->(s)
RETURN
    s.conceptId  AS concept_id,
    s.name       AS name,
    s.semanticTag AS semantic_tag,
    r.evidence   AS evidence,
    r.context    AS context
ORDER BY s.semanticTag, s.name
"""


def _pick_encounter_id() -> str:
    """Return an encounter_id from the audit DB (a has_issues one if possible)."""
    import sqlite3

    if not AUDIT_DB.exists():
        raise FileNotFoundError(f"Audit DB not found at {AUDIT_DB}")
    db = sqlite3.connect(str(AUDIT_DB))
    row = db.execute(
        "SELECT encounter_id FROM encounters "
        "WHERE status='done' AND result_json LIKE '%has_issues%' "
        "ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    if not row:
        row = db.execute(
            "SELECT encounter_id FROM encounters WHERE status='done' LIMIT 1"
        ).fetchone()
    db.close()
    if not row:
        raise RuntimeError("No completed encounters in audit DB yet.")
    return row[0]


def _assertion(context) -> str:
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return "present"
    if isinstance(context, dict):
        return context.get("assertion", "present")
    return "present"


def main() -> None:
    eid = sys.argv[1] if len(sys.argv) > 1 else _pick_encounter_id()
    print(f"Encounter: {eid}\n")

    client = PatientGraphClient()
    splitter = SentenceSplitter()

    # -- Load encounter text
    rows = client.run(_Q_ENCOUNTER, eid=eid)
    if not rows:
        print(f"Encounter {eid} not found in Neo4j.")
        return
    text = str(rows[0].get("text") or "")
    date = rows[0].get("date", "?")
    print(f"Date: {date}")
    print(
        f"Text ({len(text)} chars):\n  {text[:400]}...\n"
        if len(text) > 400
        else f"Text:\n  {text}\n"
    )

    # -- Existing coded links
    coded = client.run(_Q_CODED, eid=eid)
    print(f"Existing DOCUMENTS ({len(coded)} links):")
    for c in coded:
        a = _assertion(c.get("context"))
        print(
            f"  [{c.get('semantic_tag','?'):<18}] {c.get('concept_id','?')}  "
            f"{c.get('name','?')}  (evidence={c.get('evidence','?')!r}  assertion={a})"
        )

    # -- LLM extraction
    print(f"\nRunning LLMExtractor (tier=small)...")
    extractor = LLMExtractor()
    if not extractor.is_available():
        print(
            "LLMExtractor is NOT available -- check PIPELINE_MODEL_PROVIDER and AWS credentials."
        )
        return
    print(f"Model: {extractor.model_name}\n")

    sentences = splitter.split(text)
    print(f"Sentences ({len(sentences)}):")
    for s in sentences[:5]:
        print(f"  [{getattr(s,'sentence_id','?')}] {getattr(s,'text','')[:80]}")
    if len(sentences) > 5:
        print(f"  ... ({len(sentences) - 5} more)")

    # Raw LLM call to see the response directly
    from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
    from services.coding_worker.app.pipeline.llm_extractor import _OUTPUT_FORMAT

    system = EXTRACTION_SYSTEM_V1 + _OUTPUT_FORMAT
    user_msg = extractor._build_user_prompt(text, sentences)
    resp = extractor.client.converse(
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=2048,
        temperature=0.0,
    )
    print(f"\nRaw LLM response (first 800 chars):\n{resp.text[:800]}\n")

    items = extractor.extract_batch(text, sentences)

    print(f"LLM extracted {len(items)} items:")
    for item in items:
        print(
            f"  [{item.semantic_tag:<18}] text={item.text!r:<40}  "
            f"lookup={item.normalized!r}  assertion={item.assertion}"
        )

    # -- Diff: what did LLM find that is NOT in existing coded?
    existing_evidence = {
        str(c.get("evidence", "")).lower() for c in coded if c.get("evidence")
    }
    existing_names = {str(c.get("name", "")).lower() for c in coded if c.get("name")}
    new_items = [
        i
        for i in items
        if i.text.lower() not in existing_evidence
        and i.normalized.lower() not in existing_names
    ]
    print(f"\nNEW (not in existing coded): {len(new_items)}")
    for item in new_items:
        print(
            f"  [{item.semantic_tag:<18}] {item.text!r}  "
            f"lookup={item.normalized!r}  assertion={item.assertion}"
        )

    client.close()


if __name__ == "__main__":
    main()
