"""Quick check that fast-track referral surface forms exist and map correctly."""

from __future__ import annotations

import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
u = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
p = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_Q = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WHERE sf.text IN $forms
RETURN sf.text AS form, c.id AS cid, c.preferredTerm AS pt, r.confidence AS conf
ORDER BY sf.text
"""

CHECK_FORMS = [
    "fast track referral for suspected lung cancer",
    "fast track referral for suspected mesothelioma",
    "fast track referral for suspected pancreatic cancer",
    "fast track referral for suspected upper gastrointestinal cancer",
    "fast track referral for suspected colorectal cancer",
    "fast track referral for suspected lower gastrointestinal cancer",
    "fast track referral for suspected bladder cancer",
    "fast track referral for suspected prostate cancer",
    "fast track referral for suspected breast cancer",
    "fast track referral for suspected gynaecological cancer",
    "fast track referral for suspected skin cancer",
    "fast track referral for suspected head and neck cancer",
]

driver = GraphDatabase.driver(uri, auth=(u, p))
with driver.session() as s:
    rows = list(s.run(_Q, forms=CHECK_FORMS))

driver.close()

found = {r["form"] for r in rows}
for r in rows:
    print(f"  OK   {r['form']!r:60s} -> {r['cid']} (conf={r['conf']})")

for form in CHECK_FORMS:
    if form not in found:
        print(f"  MISS {form!r}")
