"""Seed a pulled validation bundle into a local Neo4j graph.

Atlas trace:
  DO: DO-58BD2EA0
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-58BD2EA0")

Creates Patient / ReferralRequest / DocumentReference stubs when they
are missing, then upserts :Chunk nodes via UPSERT_CHUNK. Refuses a
remote Neo4j URI unless --allow-remote is set.

Usage:
    python scripts/seed_chunks_to_local_neo4j.py --input-dir output/chunks/0001
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.chunking.validation_bundle import ValidationBundle, load_bundle  # noqa: E402
from libs.cypher.chunk_queries import UPSERT_CHUNK  # noqa: E402

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_ENSURE_STUBS = """
MERGE (p:Patient {id: $patient_id})
ON CREATE SET p.source = 'validation_seed'
MERGE (rr:ReferralRequest {id: $referral_id})
ON CREATE SET rr.source = 'validation_seed'
MERGE (rr)-[:FOR_PATIENT]->(p)
MERGE (dr:DocumentReference {id: $document_reference_id})
ON CREATE SET dr.source = 'validation_seed',
              dr.title = $title
MERGE (rr)-[:HAS_DOCUMENT]->(dr)
RETURN toString(dr.id) AS document_reference_id
"""


class RemoteGraphRefused(RuntimeError):
    """Raised when the seed script would write to a non-local graph."""


def assert_local_graph(uri: str, allow_remote: bool) -> None:
    """Refuse a remote Neo4j URI unless the caller opts in."""
    if allow_remote:
        return
    host = (urlparse(uri).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return
    raise RemoteGraphRefused(
        f"Refusing to write to {uri!r}. Point NEO4J_URI at localhost "
        "or pass --allow-remote."
    )


def _upsert_one(client: Any, record: dict[str, Any], tenant_id: str) -> None:
    client.run(
        UPSERT_CHUNK,
        document_reference_id=str(record["document_reference_id"]),
        chunk_id=str(record["chunk_id"]),
        text=str(record.get("text") or ""),
        sha256=str(record.get("sha256") or ""),
        char_start=int(record.get("char_start") or 0),
        char_end=int(record.get("char_end") or 0),
        ordinal=int(record.get("ordinal") or 0),
        tenant_id=tenant_id,
    )


def seed_bundle(
    client: Any,
    bundle: ValidationBundle,
    tenant_id: str = "validation",
) -> dict[str, int]:
    """Write stub graph nodes and upsert each chunk record."""
    patient_id = str(bundle.manifest.get("patient_id") or "validation-patient")
    referral_id = str(bundle.manifest.get("referral_id") or bundle.path.name)
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for record in bundle.chunks:
        doc_id = str(record.get("document_reference_id") or "")
        if not doc_id:
            continue
        by_doc.setdefault(doc_id, []).append(record)
    for doc_id, records in by_doc.items():
        client.run(
            _ENSURE_STUBS,
            patient_id=patient_id,
            referral_id=referral_id,
            document_reference_id=doc_id,
            title=doc_id,
        )
        for record in records:
            _upsert_one(client, record, tenant_id)
    return {"doc_count": len(by_doc), "chunk_count": len(bundle.chunks)}


def _load_env() -> None:
    from dotenv import load_dotenv

    for name in ("secrets/.env", "secrets/.env.secrets", ".env"):
        load_dotenv(ROOT / name, override=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--tenant-id", default="validation")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permit writes when NEO4J_URI is not localhost.",
    )
    args = parser.parse_args()

    _load_env()
    uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_PATIENT_URI") or ""
    try:
        assert_local_graph(uri, allow_remote=args.allow_remote)
    except RemoteGraphRefused as exc:
        print(str(exc))
        return 1

    bundle = load_bundle(pathlib.Path(args.input_dir))
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        summary = seed_bundle(client, bundle, tenant_id=args.tenant_id)
    finally:
        client.close()
    print(
        f"seeded docs={summary['doc_count']} chunks={summary['chunk_count']} "
        f"into {uri}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
