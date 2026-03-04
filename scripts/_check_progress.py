"""Quick progress check for verification pipeline."""
import sys, os, warnings
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pw = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, pw))

with driver.session() as s:
    r1 = s.run("MATCH (t:TrainingLabel) WHERE t.include = true RETURN count(t) AS n").single()["n"]
    r2 = s.run("MATCH (t:TrainingLabel) WHERE t.include = true AND t.verified_at IS NOT NULL RETURN count(t) AS n").single()["n"]
    r3 = s.run("MATCH (cr:CodingReview) RETURN count(cr) AS n").single()["n"]

driver.close()

pct = (r2 * 100.0 / r1) if r1 > 0 else 0
print(f"Total: {r1:,}  |  Verified: {r2:,} ({pct:.1f}%)  |  Remaining: {r1-r2:,}  |  CodingReviews: {r3:,}")
