import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())

from libs.neo4j_client.client import KnowledgeGraphClient
from libs.cypher.post_processor_rule_queries import UPSERT_POST_PROCESSOR_RULE

RULES = [
    {
        "rule_id": "suppress_approx_2cm",
        "active": True,
        "priority": 100,
        "action": "suppress",
        "match_text": "approximately 2cm",
        "match_label": None,
        "context_regex": None,
        "window_chars": 40,
        "rewrite_text": None,
        "rewrite_label": None,
        "created_by": "system",
        "notes": "Suppress meaningless bare size",
    },
    {
        "rule_id": "suppress_approx_3cm",
        "active": True,
        "priority": 100,
        "action": "suppress",
        "match_text": "approximately 3cm",
        "match_label": None,
        "context_regex": None,
        "window_chars": 40,
        "rewrite_text": None,
        "rewrite_label": None,
        "created_by": "system",
        "notes": "Suppress meaningless bare size",
    },
    {
        "rule_id": "rewrite_lost_3kg",
        "active": True,
        "priority": 100,
        "action": "rewrite",
        "match_text": "lost approximately 3kg",
        "match_label": None,
        "context_regex": None,
        "window_chars": 40,
        "rewrite_text": "weight loss",
        "rewrite_label": None,
        "created_by": "system",
        "notes": "Rewrite specific weight loss to SNOMED-codable concept",
    },
]

def seed_rules():
    client = KnowledgeGraphClient()
    count = 0
    with client.session() as session:
        for rule in RULES:
            res = session.run(UPSERT_POST_PROCESSOR_RULE, **rule).single()
            if res:
                count += 1
                
    print(f"Upserted {count} post-processor rules.")

if __name__ == "__main__":
    seed_rules()
