"""Run the NLP pipeline on all patient encounters and output structured JSON."""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.terminology.nlp.extensions import set_extensions
from services.terminology.nlp.components import abbreviation_detector  # noqa: F401
from services.terminology.nlp.components import read_code_extractor  # noqa: F401
from services.terminology.nlp.components import entity_linker  # noqa: F401
from services.terminology.nlp.components import value_unit_extractor  # noqa: F401
from services.terminology.nlp.components import date_extractor  # noqa: F401
from services.terminology.nlp.components import confidence_scorer  # noqa: F401

import spacy

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATIENT_ID = "4202301609"


def build_pipeline():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("abbreviation_detector", config={"language_code": "en_gb"})
    nlp.add_pipe("read_code_extractor")
    nlp.add_pipe("value_unit_extractor")
    nlp.add_pipe("date_extractor")
    nlp.add_pipe("confidence_scorer")
    return nlp


def query_encounters(driver, patient_id):
    with driver.session() as session:
        result = session.run(
            "MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter) "
            "RETURN p.id AS patient_id, e.date AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return [dict(r) for r in result]


def lookup_snomed_for_read_codes(driver, read_codes):
    """Batch-lookup SNOMED concepts for a set of Read codes via Neo4j."""
    if not read_codes:
        return {}
    with driver.session() as session:
        result = session.run(
            "UNWIND $codes AS rc "
            "OPTIONAL MATCH (r)-[:MAPS_TO]->(s:Concept) "
            "WHERE r.code = rc AND s.terminology = 'SNOMED' "
            "RETURN rc AS read_code, "
            "       s.code AS snomed_code, "
            "       s.term AS snomed_term "
            "LIMIT 5000",
            codes=list(read_codes),
        )
        mapping = {}
        for rec in result:
            rc = rec["read_code"]
            if rec["snomed_code"]:
                mapping[rc] = {
                    "snomed_code": rec["snomed_code"],
                    "snomed_term": rec["snomed_term"],
                }
        return mapping


def serialise_date(val):
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return str(val) if val else None


def build_entity_record(ent, enc_date, enc_text, snomed_map):
    """Build a single entity record dict."""
    rec = {
        "date": serialise_date(enc_date),
        "span": ent.text,
        "label": ent.label_,
        "start_char": ent.start_char,
        "end_char": ent.end_char,
        "snomed_code": None,
        "snomed_term": None,
        "read_code": None,
        "confidence": round(ent._.confidence, 3),
        "encounter_text": enc_text,
    }

    if ent._.read_code:
        rec["read_code"] = ent._.read_code
        mapped = snomed_map.get(ent._.read_code)
        if mapped:
            rec["snomed_code"] = mapped["snomed_code"]
            rec["snomed_term"] = mapped["snomed_term"]

    if ent._.measurement_type:
        rec["measurement_type"] = ent._.measurement_type
        rec["value"] = ent._.value
        rec["unit"] = ent._.unit

    if ent._.temporal_type:
        rec["temporal_type"] = ent._.temporal_type
        rec["date_value"] = serialise_date(ent._.date_value)

    return rec


def main():
    load_dotenv("secrets/.env")
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    pwd = os.getenv("NEO4J_PASSWORD")

    print(f"Connecting to {uri} ...", file=sys.stderr)
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()

    encounters = query_encounters(driver, PATIENT_ID)
    print(
        f"Patient {PATIENT_ID}: {len(encounters)} encounters",
        file=sys.stderr,
    )

    nlp = build_pipeline()

    # --- Pass 1: run pipeline, collect Read codes for batch SNOMED lookup ---
    processed = []
    all_read_codes = set()

    for enc in encounters:
        text = enc.get("text") or ""
        enc_date = enc.get("date")
        if not text.strip():
            continue
        doc = nlp(text)
        processed.append((enc_date, text, doc))
        for ent in doc.ents:
            if ent._.read_code:
                all_read_codes.add(ent._.read_code)

    print(
        f"Extracted {len(all_read_codes)} unique Read codes, "
        f"looking up SNOMED mappings ...",
        file=sys.stderr,
    )
    snomed_map = lookup_snomed_for_read_codes(driver, all_read_codes)
    driver.close()
    print(
        f"Found SNOMED mappings for {len(snomed_map)}/{len(all_read_codes)} codes",
        file=sys.stderr,
    )

    # --- Pass 2: build JSON output ---
    records = []
    for enc_date, text, doc in processed:
        for ent in doc.ents:
            records.append(build_entity_record(ent, enc_date, text, snomed_map))

    output = {
        "patient_id": PATIENT_ID,
        "total_encounters": len(encounters),
        "processed_encounters": len(processed),
        "total_entities": len(records),
        "unique_read_codes": len(all_read_codes),
        "snomed_mapped": len(snomed_map),
        "entities": records,
    }

    out_path = _ROOT / "scripts" / "pipeline_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nWritten {len(records)} entities to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
