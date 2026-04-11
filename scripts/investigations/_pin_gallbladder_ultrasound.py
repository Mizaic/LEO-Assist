"""Pin gallbladder and upper abdominal ultrasound action surface forms.

  169250003 | Ultrasound scan of gallbladder (procedure)
  312235006 | Ultrasonography of upper abdomen (procedure)  -- broad fallback

Also pins direct-access ultrasound phrases used in NG12 1.2.10 action.
"""

import os, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

TOKEN_RE = re.compile(r"[a-z0-9]+")


def norm(t):
    return " ".join(TOKEN_RE.findall(t.lower()))


kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# (display_form, concept_id, fsn, semantic_tag)
PINS = [
    # 169250003 | Ultrasound scan of gallbladder (procedure)
    (
        "ultrasound scan of gallbladder",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "ultrasonography of gallbladder",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "gallbladder ultrasound",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "direct access ultrasound of gallbladder",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "urgent direct access ultrasound scan to assess for gall bladder cancer",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "urgent direct access ultrasound scan of abdomen to assess for gall bladder cancer",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "urgent ultrasound to assess gall bladder",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    (
        "gallbladder cancer ultrasound",
        "169250003",
        "Ultrasound scan of gallbladder (procedure)",
        "procedure",
    ),
    # 312235006 | Ultrasonography of upper abdomen (procedure) -- broad fallback
    (
        "ultrasonography of upper abdomen",
        "312235006",
        "Ultrasonography of upper abdomen (procedure)",
        "procedure",
    ),
    (
        "ultrasound upper abdomen",
        "312235006",
        "Ultrasonography of upper abdomen (procedure)",
        "procedure",
    ),
    (
        "upper abdominal ultrasound",
        "312235006",
        "Ultrasonography of upper abdomen (procedure)",
        "procedure",
    ),
    (
        "direct access upper abdominal ultrasound",
        "312235006",
        "Ultrasonography of upper abdomen (procedure)",
        "procedure",
    ),
]

UPSERT = """
MERGE (c:Concept {id: $cid})
ON CREATE SET c.fsn = $fsn, c.semantic_tag = $semantic_tag, c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.created_at = datetime(), sf.status = 'approved'
SET sf.form = $form,
    sf.source = 'manual_pin',
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
SET m.confidence = 1.0,
    m.approved_at = datetime(),
    m.provenance  = 'ng12_guideline_pin',
    m.pinned      = true
RETURN sf.normalized AS normalized, c.id AS cid
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
ok = 0
seen: set[tuple[str, str]] = set()
with driver.session() as s:
    for form, cid, fsn, semantic_tag in PINS:
        normalized = norm(form)
        key = (normalized, cid)
        if key in seen:
            continue
        seen.add(key)
        row = s.run(
            UPSERT,
            normalized=normalized,
            form=form,
            cid=cid,
            fsn=fsn,
            semantic_tag=semantic_tag,
        ).single()
        if row:
            print(f"  OK  {row['normalized']!r:65s} -> {row['cid']}")
            ok += 1
        else:
            print(f"  ERR {normalized!r}")
driver.close()
print(f"\nDone. {ok}/{len(PINS)} pinned.")
