"""Check what episode-related node labels exist and their relationship counts."""
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
    for label in ("EpisodeOfCare", "CancerEpisode", "Episode"):
        n = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
        if n:
            rels = s.run(
                f"MATCH (n:{label})-[r]-() RETURN type(r) AS t, count(r) AS c"
            )
            rel_summary = ", ".join(f"{r['t']}={r['c']}" for r in rels)
            print(f"{label}: {n} nodes  |  relationships: {rel_summary or 'none'}")
        else:
            print(f"{label}: 0 nodes")
client.close()
