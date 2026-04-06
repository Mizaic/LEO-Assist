"""Delete all EpisodeOfCare nodes and their relationships."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()
with client.session() as s:
    before = s.run("MATCH (n:EpisodeOfCare) RETURN count(n) AS c").single()["c"]
    print(f"EpisodeOfCare nodes before: {before}")
    deleted = 0
    while True:
        r = s.run(
            "MATCH (n:EpisodeOfCare) "
            "WITH n LIMIT 500 "
            "DETACH DELETE n "
            "RETURN count(*) AS c"
        ).single()["c"]
        deleted += r
        if r == 0:
            break
    after = s.run("MATCH (n:EpisodeOfCare) RETURN count(n) AS c").single()["c"]
    print(f"Deleted: {deleted}  |  Remaining: {after}")
client.close()
