"""Check current state of ncda-treatment ValueSet and analytics API port."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient

kg = KnowledgeGraphClient()
try:
    rows = kg.run(
        "MATCH (v:ValueSet {id: $vs_id}) "
        "RETURN v.name AS name, v.milestoneType AS mt, v.rawJson AS rj",
        vs_id="ncda-treatment",
    )
    if rows:
        rj = rows[0].get("rj")
        if rj:
            vs = json.loads(rj) if isinstance(rj, str) else rj
            count = sum(
                len(inc.get("concept") or [])
                for inc in (vs.get("compose") or {}).get("include") or []
            )
            existing_codes = [
                c.get("code")
                for inc in (vs.get("compose") or {}).get("include") or []
                for c in inc.get("concept") or []
            ]
            print(f"ncda-treatment exists, concepts in rawJson: {count}")
            print(f"  First 5 codes: {existing_codes[:5]}")
        else:
            print("ncda-treatment exists but rawJson is EMPTY")
    else:
        print("ncda-treatment: NOT FOUND in graph")

    rows2 = kg.run(
        "MATCH (d:AuditDomain {id: $did})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
        "RETURN v.id AS vid ORDER BY vid",
        did="cancer_audit",
    )
    print(f"\nSubdomains under cancer_audit ({len(rows2 or [])} total):")
    for r in (rows2 or []):
        print(f"  {r['vid']}")

    # Check analytics API port from env
    import os
    analytics_url = os.environ.get("ANALYTICS_API_URL", "http://localhost:8003")
    terminology_url = os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8001")
    print(f"\nAnalytics API URL : {analytics_url}")
    print(f"Terminology API URL: {terminology_url}")
finally:
    kg.close()
