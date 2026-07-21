import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.db.neo4j_client import CodingGraphClient
client = CodingGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario {case_id: 'brain_cns_known_primary_001'}) RETURN c.expected_strings as expected").single()
    print("Raw from DB:", res["expected"])
    print("Type from DB:", type(res["expected"]))
