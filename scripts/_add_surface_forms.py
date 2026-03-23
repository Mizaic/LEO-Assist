"""One-off: add surface form gaps identified in training evaluation report 2026-03-05."""
from dotenv import load_dotenv
load_dotenv("secrets/.env")

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import UPSERT_SURFACE_FORM_MAPPING

SURFACE_FORMS = [
    # overtreated — SNOMED 395016000 | Overtreated (finding)
    dict(
        normalized="overtreated",
        form="overtreated",
        concept_id="395016000",
        confidence=1.0,
        source="manual",
        provenance="eval_gap_correction",
        created_by="robert.smith",
    ),
    # cosmocol — brand name for macrogol, SNOMED 8030004 | Macrogol (substance)
    dict(
        normalized="cosmocol",
        form="Cosmocol",
        concept_id="8030004",
        confidence=1.0,
        source="manual",
        provenance="eval_gap_correction",
        created_by="robert.smith",
    ),
    # diannette — brand name for co-cyprindiol; UK dm+d 9260201000001107 not in graph
    # Map to 126120000 | Cyproterone acetate (substance) — the primary active ingredient
    dict(
        normalized="diannette",
        form="Diannette",
        concept_id="126120000",
        confidence=0.9,
        source="manual",
        provenance="eval_gap_correction",
        created_by="robert.smith",
    ),
    # full sentence extraction — lower confidence, maps same concept
    dict(
        normalized="stopped diannette a year ago",
        form="stopped Diannette a year ago",
        concept_id="126120000",
        confidence=0.6,
        source="manual",
        provenance="eval_gap_correction",
        created_by="robert.smith",
    ),
    # dry giloy — Ayurvedic supplement, best fit SNOMED 418165002 | Herbal medicine agent (substance)
    dict(
        normalized="dry giloy",
        form="Dry Giloy",
        concept_id="418165002",
        confidence=0.7,
        source="manual",
        provenance="eval_gap_correction",
        created_by="robert.smith",
    ),
]

client = KnowledgeGraphClient()
try:
    for sf in SURFACE_FORMS:
        rows = client.run(UPSERT_SURFACE_FORM_MAPPING, **sf)
        if rows:
            r = rows[0]
            print(f"OK   {r['normalized']!r:45s}  =>  {r['concept_fsn']}")
        else:
            print(f"MISS {sf['normalized']!r:45s}  — concept {sf['concept_id']} not found in graph")
finally:
    client.close()
