"""Live test: run the NLP pipeline against real patient encounters from Neo4j."""

import os
import sys
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


def format_entity(ent):
    parts = [f"{ent.label_:15s}"]
    if ent._.measurement_type:
        parts.append(f"{ent._.measurement_type}={ent._.value} {ent._.unit}")
    elif ent._.read_code:
        parts.append(f"read={ent._.read_code}")
    elif ent._.temporal_type:
        parts.append(f"{ent._.temporal_type}")
    if ent._.source:
        parts.append(f"[{ent._.source}]")
    return f"{ent.text!r:35s} {' '.join(parts)}"


def main():
    load_dotenv("secrets/.env")
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    pwd = os.getenv("NEO4J_PASSWORD")
    patient_id = "4202301609"

    print(f"Connecting to {uri} ...")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    print("Connected.\n")

    encounters = query_encounters(driver, patient_id)
    print(f"Patient {patient_id}: {len(encounters)} encounters\n")
    driver.close()

    if not encounters:
        print("No encounters found.")
        return

    nlp = build_pipeline()

    totals = {
        "encounters": len(encounters),
        "with_entities": 0,
        "measurements": 0,
        "read_codes": 0,
        "dates": 0,
        "abbreviations": 0,
    }
    interesting = []

    for i, enc in enumerate(encounters):
        text = enc.get("text") or ""
        date = enc.get("date", "?")
        if not text.strip():
            continue

        doc = nlp(text)
        ents = list(doc.ents)
        abbrevs = list(doc._.abbreviations)

        if not ents and not abbrevs:
            continue

        totals["with_entities"] += 1
        totals["measurements"] += sum(
            1 for e in ents if e.label_ == "MEASUREMENT"
        )
        totals["read_codes"] += sum(
            1 for e in ents if e.label_ == "READ_CODE"
        )
        totals["dates"] += sum(1 for e in ents if e.label_ == "DATE")
        totals["abbreviations"] += len(abbrevs)

        has_clinical = any(
            e.label_ in ("MEASUREMENT", "READ_CODE") for e in ents
        )
        if has_clinical:
            interesting.append((i + 1, date, text, doc))

    # --- Summary ---
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total encounters:      {totals['encounters']}")
    print(f"  With any output:       {totals['with_entities']}")
    print(f"  Measurements found:    {totals['measurements']}")
    print(f"  Read codes found:      {totals['read_codes']}")
    print(f"  Dates found:           {totals['dates']}")
    print(f"  Abbreviations found:   {totals['abbreviations']}")

    # --- Show clinically interesting encounters ---
    print(f"\n{'=' * 80}")
    print(f"CLINICALLY INTERESTING ENCOUNTERS ({len(interesting)} with "
          f"measurements or Read codes)")
    print("=" * 80)

    for num, date, text, doc in interesting:
        print(f"\n--- Encounter {num} | {date} ---")
        preview = text[:200].replace("\n", " | ")
        print(f"  {preview}{'...' if len(text) > 200 else ''}")
        print("  Entities:")
        for ent in doc.ents:
            print(f"    {format_entity(ent)}")
        abbrevs_with_expansion = [
            a for a in doc._.abbreviations
            if a._.long_form or (len(a) == 1 and a[0]._.expanded_form)
        ]
        if abbrevs_with_expansion:
            expanded = []
            for a in abbrevs_with_expansion:
                lf = a._.long_form
                if lf:
                    expanded.append(f"{a.text}->{lf.text}")
                elif len(a) == 1 and a[0]._.expanded_form:
                    expanded.append(f"{a.text}->{a[0]._.expanded_form}")
            print(f"  Abbrevs: {', '.join(expanded)}")

    print(f"\n{'=' * 80}")
    print("Done.")


if __name__ == "__main__":
    main()
