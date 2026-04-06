"""
Pin 'suspected cancer pathway referral' and '2WW referral' alias surface forms
so the resolver finds the right FTR concept when LLMs use NHS pathway language
instead of the canonical 'fast track referral for suspected X' phrasing.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


# 276551000000108 = Fast track referral for suspected upper gastrointestinal cancer
# 276491000000101 = Fast track referral for suspected lung cancer (used for mesothelioma)
FORMS = [
    # -- Upper GI / pancreatic (suspected cancer pathway phrasing) --
    ("suspected cancer pathway referral pancreatic cancer", "276551000000108"),
    ("suspected cancer pathway referral for pancreatic cancer", "276551000000108"),
    ("suspected pancreatic cancer pathway referral", "276551000000108"),
    ("suspected cancer pathway referral upper gastrointestinal cancer", "276551000000108"),
    ("suspected cancer pathway referral upper gastrointestinal", "276551000000108"),
    ("suspected upper gastrointestinal cancer pathway referral", "276551000000108"),
    ("suspected upper gastrointestinal cancer referral", "276551000000108"),
    ("suspected oesophageal cancer referral", "276551000000108"),
    ("suspected oesophageal cancer pathway referral", "276551000000108"),
    ("suspected pancreatic cancer referral", "276551000000108"),
    ("two week wait referral pancreatic cancer", "276551000000108"),
    ("two week wait referral for suspected pancreatic cancer", "276551000000108"),
    ("two week wait referral for suspected upper gastrointestinal cancer", "276551000000108"),
    ("2 week wait referral for suspected upper gastrointestinal cancer", "276551000000108"),
    ("2ww upper gastrointestinal cancer", "276551000000108"),
    ("non urgent referral suspected pancreatic cancer", "276551000000108"),
    ("routine referral suspected pancreatic cancer", "276551000000108"),
    # -- Mesothelioma (suspected cancer pathway phrasing) --
    ("suspected cancer pathway referral mesothelioma", "276491000000101"),
    ("suspected cancer pathway referral for mesothelioma", "276491000000101"),
    ("suspected mesothelioma cancer pathway referral", "276491000000101"),
    ("suspected mesothelioma pathway referral", "276491000000101"),
    ("two week wait referral for suspected mesothelioma", "276491000000101"),
    ("non urgent referral suspected mesothelioma", "276491000000101"),
    ("routine referral suspected mesothelioma", "276491000000101"),
    # -- Lung cancer suspected pathway phrasing --
    ("suspected cancer pathway referral lung cancer", "276491000000101"),
    ("suspected cancer pathway referral for lung cancer", "276491000000101"),
    ("suspected lung cancer pathway referral", "276491000000101"),
    ("two week wait referral for suspected lung cancer", "276491000000101"),
    ("2 week wait referral lung cancer", "276491000000101"),
]

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
WITH sf, c
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.confidence = 1.0, r.source = 'manual'
RETURN sf.normalized AS norm, c.id AS cid, c.fsn AS fsn
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN c.id AS cid
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    added = skipped = errors = 0
    with driver.session() as s:
        for form, cid in FORMS:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == cid for r in existing):
                print(f"  [SKIP] {norm!r:60s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(f"  [ADD ] {norm!r:55s} -> {row['cid']} {row['fsn'][:35]}")
                added += 1
            else:
                print(f"  [ERR ] {norm!r:60s} concept {cid} not in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
