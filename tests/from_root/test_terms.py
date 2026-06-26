import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from libs.neo4j_client.client import KnowledgeGraphClient
client = KnowledgeGraphClient()
with client.session() as session:
    res = session.run("MATCH (r:ValidationRun) RETURN r.per_case_results as results ORDER BY r.completed_at DESC LIMIT 1").single()
    if res and res["results"]:
        data = json.loads(res["results"])
        print(data[0].keys())
        print("extra_strings:", data[0].get("extra_strings")[:2])
