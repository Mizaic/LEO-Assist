"""
Pin surface forms for chest X-ray / imaging findings suggestive of cancer.

These are FINDING concepts (not procedures) visible on an imaging report.
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


# Radiological FINDING concepts only (semantic tag = finding / disorder)
# Each tuple: (display_form, snomed_concept_id, brief_justification)
FORMS = [
    # Lung mass / nodule (309529002 = Lung mass (finding))
    ("lung mass", "309529002", "Lung mass (finding)"),
    ("pulmonary mass", "309529002", "Lung mass (finding)"),
    ("mass in lung", "309529002", "Lung mass (finding)"),
    # Pulmonary nodule (786838002 = Nodule of lung (disorder))
    ("lung nodule", "786838002", "Nodule of lung (disorder)"),
    ("pulmonary nodule", "786838002", "Nodule of lung (disorder)"),
    ("solitary pulmonary nodule", "427359005", "Solitary nodule of lung (finding)"),
    # Pleural effusion (already added, kept for idempotency)
    ("pleural effusion", "60046008", "Pleural effusion (disorder)"),
    ("unilateral pleural effusion", "60046008", "Pleural effusion (disorder)"),
    ("fluid in pleural cavity", "60046008", "Pleural effusion (disorder)"),
    # Hilar lymphadenopathy (87500009 = Hilar lymphadenopathy (disorder))
    ("hilar lymphadenopathy", "87500009", "Hilar lymphadenopathy (disorder)"),
    ("hilar enlargement", "87500009", "Hilar lymphadenopathy (disorder)"),
    # Mediastinal widening / mass
    ("mediastinal widening", "363646005", "Widened mediastinum (finding)"),
    ("widened mediastinum", "363646005", "Widened mediastinum (finding)"),
    ("mediastinal mass", "94147001", "Mass of mediastinum (finding)"),
    # Lung consolidation (95436008 = Lung consolidation (disorder))
    ("lung consolidation", "95436008", "Lung consolidation (disorder)"),
    ("pulmonary consolidation", "95436008", "Lung consolidation (disorder)"),
    ("lobar consolidation", "95436008", "Lung consolidation (disorder)"),
    # Ground glass opacity (9990010005 = Ground glass lung opacity (finding))
    ("ground glass opacity", "9990010005", "Ground glass lung opacity (finding)"),
    ("ground glass lung opacity", "9990010005", "Ground glass lung opacity (finding)"),
    # Collapse / atelectasis (46621007 = Atelectasis (disorder))
    ("lung collapse", "46621007", "Atelectasis (disorder)"),
    ("lobar collapse", "46621007", "Atelectasis (disorder)"),
    ("atelectasis", "46621007", "Atelectasis (disorder)"),
    # CXR abnormal finding (9990010014 = Plain X-ray of chest abnormal (finding))
    (
        "chest x ray abnormal finding",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
    ),
    (
        "abnormal chest x ray",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
    ),
    # Specific compound phrases -> lung mass as primary finding
    (
        "chest x ray findings suggestive of lung cancer",
        "309529002",
        "Lung mass (finding) - canonical CXR finding for suspected lung cancer",
    ),
    (
        "suspicious chest x ray for lung cancer",
        "309529002",
        "Lung mass (finding) - suspicious CXR in lung cancer pathway",
    ),
]

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = 'manual',
              sf.status = 'active',
              sf.created_at = datetime()
SET sf.form = $form
WITH sf, c
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.confidence = 1.0, r.source = 'manual'
RETURN sf.normalized AS norm, c.id AS cid, c.fsn AS fsn
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN c.id AS cid, c.fsn AS fsn
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    added = 0
    skipped = 0
    errors = 0
    with driver.session() as s:
        for form, cid, note in FORMS:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == cid for r in existing):
                print(f"  [SKIP] {norm!r:55s} already -> {cid}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(
                    f"  [ADD ] {norm!r:55s} -> {row['cid']:15s}" f" {row['fsn'][:45]}"
                )
                added += 1
            else:
                print(f"  [ERR ] {norm!r:55s} concept {cid} not found in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
