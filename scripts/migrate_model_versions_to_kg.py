"""One-time migration: copy ModelVersion nodes from Patient Graph to Knowledge Graph.

The model registry was moved to the Knowledge Graph, but existing ModelVersion
nodes were registered against the Patient Graph.  This script reads them from
the Patient Graph and writes them to the Knowledge Graph without deleting the
originals (safe to re-run).

Run:
    python scripts/migrate_model_versions_to_kg.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from dotenv import load_dotenv
    load_dotenv("secrets/.env.config", override=False)
    load_dotenv("secrets/.env", override=False)
except ImportError:
    pass
try:
    from libs.keyvault.loader import load_keyvault_secrets
    load_keyvault_secrets()
except Exception:
    pass

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.cypher.model_registry_queries import CREATE_MODEL_VERSION, SET_ACTIVE_VERSION


def main() -> None:
    pg = PatientGraphClient()
    with pg.session() as s:
        nodes = s.run("MATCH (m:ModelVersion) RETURN properties(m) AS p").data()
        cfg   = s.run("MATCH (c:ModelRegistryConfig) RETURN c.active_version AS av").data()
    pg.close()

    active_ver = cfg[0]["av"] if cfg else None
    print(f"Found {len(nodes)} ModelVersion node(s) in Patient Graph  (active={active_ver})")

    if not nodes:
        print("Nothing to migrate.")
        return

    kg = KnowledgeGraphClient()
    with kg.session() as s:
        for row in nodes:
            p   = row["p"]
            ver = p.get("version") or p.get("model_version") or ""
            s.run(
                CREATE_MODEL_VERSION,
                version=ver,
                model_name=p.get("model_name", ""),
                model_path=p.get("model_path", ""),
                training_dataset_version=p.get("training_dataset_version", ""),
                schema_version=p.get("schema_version", "1.0"),
                deid_version=p.get("deid_version", "1.0"),
                artifact_uri=p.get("artifact_uri", ""),
                status=p.get("status", "canary"),
                offline_precision=p.get("offline_precision"),
                offline_recall=p.get("offline_recall"),
                canary_precision=p.get("canary_precision"),
                canary_recall=p.get("canary_recall"),
                canary_cohort=p.get("canary_cohort"),
                rollback_target_version=p.get("rollback_target_version"),
                registered_at=str(p.get("registered_at", "")),
                promoted_at=p.get("promoted_at"),
                notes=p.get("notes", ""),
            )
            print(f"  Migrated: {ver!r}  status={p.get('status')}")

        if active_ver:
            s.run(SET_ACTIVE_VERSION, active_version=active_ver)
            print(f"  Set active version: {active_ver}")

    kg.close()
    print("Done.")


if __name__ == "__main__":
    main()
