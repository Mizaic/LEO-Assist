import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from libs.neo4j_client.client import KnowledgeGraphClient

client = KnowledgeGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario {case_id: 'brain_cns_known_primary_001'}) RETURN c.expected_strings as expected").single()
    print(res["expected"])
