"""Migrate model registry from JSON file to Neo4j.

Run once after switching MODEL_REGISTRY_STORE=neo4j to copy existing
records from the JSON file into the Patient Graph.

Usage (from repo root, with .venv active):
    python scripts/migrate_model_registry_to_neo4j.py [--json-path PATH]

Reads MODEL_REGISTRY_STORE_PATH or .model_cache/model_registry.json by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load secrets
env_path = REPO_ROOT / "secrets" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

from libs.model_registry.registry import ModelRecord, ModelStatus
from libs.model_registry.neo4j_registry import Neo4jModelRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate model registry JSON to Neo4j")
    parser.add_argument(
        "--json-path",
        default=os.getenv("MODEL_REGISTRY_STORE_PATH")
        or str(REPO_ROOT / ".model_cache" / "model_registry.json"),
        help="Path to source JSON file",
    )
    args = parser.parse_args()

    src = Path(args.json_path)
    if not src.exists():
        print(f"JSON file not found: {src}")
        return 1

    data = json.loads(src.read_text(encoding="utf-8"))
    records = data.get("records", {})
    active_version = data.get("active_version")

    if not records:
        print("No records to migrate.")
        return 0

    registry = Neo4jModelRegistry()
    migrated = 0
    for ver, rec_dict in records.items():
        existing = registry.get(ver)
        if existing:
            print(f"  Skip {ver} (already in Neo4j)")
            continue
        rec = ModelRecord.from_dict(rec_dict)
        registry.register(rec)
        print(f"  Migrated {ver} (status={rec.status})")
        migrated += 1

    if migrated > 0:
        version_to_activate = active_version
        if not version_to_activate:
            version_to_activate = list(records.keys())[0]
            print(
                f"  active_version was null; using first record: {version_to_activate}"
            )
        existing = registry.get(version_to_activate)
        if existing:
            registry._set_active_version(version_to_activate)
            print(f"  Set active_version={version_to_activate}")

    print(f"\nMigrated {migrated} record(s) to Neo4j.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
