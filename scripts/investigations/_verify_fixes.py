"""Verify systematic fixes applied correctly."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()
try:
    with client.session() as session:
        # Check NAD codes
        nad = session.run(
            "MATCH ()-[r:DOCUMENTS]->(s)"
            " WHERE s.conceptId = 281900007 RETURN count(r) AS cnt"
        ).single()
        print(f"Remaining NAD 'Normal appearance' (281900007): {nad['cnt']}")

        # Check GP surgery on phone
        gp_phone = session.run("""
            MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
            WHERE s.conceptId = 185202000
              AND (
                toLower(e.text) CONTAINS 'telephone consultation' OR
                toLower(e.text) CONTAINS 'phone consultation' OR
                toLower(e.text) CONTAINS 'telephone call' OR
                toLower(e.text) CONTAINS 'video consultation' OR
                toLower(e.text) CONTAINS 'video call'
              )
            RETURN count(r) AS cnt
        """).single()
        print(f"Remaining GP-surgery on phone text: {gp_phone['cnt']}")

        # Check GP surgery total (should be reduced but not zero)
        gp_total = session.run(
            "MATCH ()-[r:DOCUMENTS]->(s)"
            " WHERE s.conceptId = 185202000 RETURN count(r) AS cnt"
        ).single()
        print(f"Total remaining 'Seen in GP surgery' codes: {gp_total['cnt']}")

finally:
    client.close()
