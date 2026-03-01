"""Quick compatibility test: local Bio_ClinicalBERT embedding vs Neo4j encounter_vector_index."""
import os, sys, logging
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(__import__("pathlib").Path(__file__).resolve().parents[1] / "secrets" / ".env")

logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

model_name = os.environ.get("VECTOR_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
dim = int(os.environ.get("VECTOR_DIMENSION", 768))
print(f"Model: {model_name}  dim={dim}")

model = SentenceTransformer(model_name)

MILESTONE_ANCHORS = [
    ("FAST_TRACK_REFERRAL",   "fast track referral for suspected cancer 2WW"),
    ("FIRST_SEEN",            "seen in fast track suspected cancer clinic"),
    ("DIAGNOSIS_CONFIRMED",   "confirmed diagnosis of cancer malignancy"),
    ("FIRST_TREATMENT",       "started cancer treatment chemotherapy radiotherapy"),
]

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)

print()
for milestone, phrase in MILESTONE_ANCHORS:
    emb = model.encode(phrase, normalize_embeddings=True).tolist()
    print(f"--- {milestone} ---")
    print(f"  Query phrase : '{phrase}'")
    print(f"  Embedding    : {len(emb)} dims, first 3 = {[round(v, 5) for v in emb[:3]]}")

    with driver.session() as s:
        rows = s.run(
            "CALL db.index.vector.queryNodes('encounter_vector_index', 5, $emb) "
            "YIELD node, score "
            "RETURN node.text AS txt, score ORDER BY score DESC",
            emb=emb,
        ).data()

    if not rows:
        print("  WARNING: no results — index may be empty or dimensions mismatch")
    else:
        print(f"  Top {len(rows)} hits:")
        for i, r in enumerate(rows, 1):
            snippet = (r["txt"] or "").replace("\n", " ")[:110]
            print(f"    {i}. score={r['score']:.4f}  |  {snippet}")
    print()

driver.close()
print("Test complete.")
