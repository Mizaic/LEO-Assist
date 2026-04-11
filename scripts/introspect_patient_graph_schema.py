#!/usr/bin/env python3
"""Introspect the Patient Graph Neo4j schema: nodes, properties, relationships, relationship properties.

Uses NEO4J_URI from secrets/.env. Outputs JSON to stdout for piping to a file.

Usage:
    python scripts/introspect_patient_graph_schema.py
    python scripts/introspect_patient_graph_schema.py > patient_graph_schema.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on path for libs
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / "secrets" / ".env")

from libs.neo4j_client.client import PatientGraphClient


def run(client: PatientGraphClient, query: str, **params) -> list[dict]:
    """Run a query and return list of record dicts."""
    with client.session() as session:
        result = session.run(query, parameters=params or {})
        return [dict(record) for record in result]


def get_node_labels(client: PatientGraphClient) -> list[str]:
    """Get all node labels in the graph."""
    records = run(client, "CALL db.labels()")
    return [r.get("label", list(r.values())[0] if r else "") for r in records if r]


def get_relationship_types(client: PatientGraphClient) -> list[str]:
    """Get all relationship types in the graph."""
    try:
        records = run(client, "CALL db.relationshipTypes()")
        return [
            r.get("relationshipType", list(r.values())[0] if r else "")
            for r in records
            if r
        ]
    except Exception:
        return []


def get_node_properties(client: PatientGraphClient, label: str) -> list[dict]:
    """Get properties for a node label. Tries db.schema.nodeTypeProperties() first."""
    try:
        records = run(
            client,
            """
            CALL db.schema.nodeTypeProperties()
            YIELD nodeLabels, propertyName, propertyTypes, mandatory
            WHERE $label IN nodeLabels
            RETURN propertyName AS property_name, propertyTypes AS property_types, mandatory
            ORDER BY propertyName
            """,
            label=label,
        )
        if records:
            return [
                {
                    "property_name": r.get("property_name", r.get("propertyName")),
                    "property_types": r.get(
                        "property_types", r.get("propertyTypes", [])
                    ),
                    "mandatory": r.get("mandatory", False),
                }
                for r in records
            ]
    except Exception:
        pass

    # Fallback: sample a node and get keys
    try:
        safe_label = f"`{label}`" if ":" in label or "-" in label else label
        records = run(
            client,
            f"MATCH (n:{safe_label}) WITH n LIMIT 100 UNWIND keys(n) AS k RETURN DISTINCT k ORDER BY k",
        )
        return [
            {"property_name": r["k"], "property_types": [], "mandatory": False}
            for r in records
        ]
    except Exception:
        return []


def get_relationships_for_label(client: PatientGraphClient, label: str) -> list[dict]:
    """Get relationships involving this label (outgoing and incoming)."""
    rels: list[dict] = []
    safe = f"`{label}`" if ":" in label or "-" in label else label

    try:
        # Outgoing
        out_records = run(
            client,
            f"""
            MATCH (n:{safe})-[r]->(m)
            WITH type(r) AS rel_type, labels(m) AS target_labels
            RETURN rel_type, target_labels, 'OUTGOING' AS direction
            LIMIT 200
            """,
        )
        for r in out_records:
            rels.append(
                {
                    "relationship_type": r.get("rel_type", ""),
                    "direction": "OUTGOING",
                    "target_labels": r.get("target_labels", []),
                }
            )

        # Incoming
        in_records = run(
            client,
            f"""
            MATCH (n:{safe})<-[r]-(m)
            WITH type(r) AS rel_type, labels(m) AS source_labels
            RETURN rel_type, source_labels AS target_labels, 'INCOMING' AS direction
            LIMIT 200
            """,
        )
        for r in in_records:
            rels.append(
                {
                    "relationship_type": r.get("rel_type", ""),
                    "direction": "INCOMING",
                    "target_labels": r.get("target_labels", []),
                }
            )

        # Deduplicate
        seen = set()
        unique = []
        for rel in rels:
            key = (
                rel["relationship_type"],
                rel["direction"],
                tuple(rel["target_labels"]),
            )
            if key not in seen:
                seen.add(key)
                unique.append(rel)
        return unique
    except Exception:
        return []


def get_relationship_properties(client: PatientGraphClient) -> list[dict]:
    """Get relationship types and their properties."""
    result: list[dict] = []
    try:
        records = run(
            client,
            """
            MATCH (a)-[r]->(b)
            WITH type(r) AS rel_type, keys(r) AS rel_keys
            RETURN DISTINCT rel_type, rel_keys
            ORDER BY rel_type
            LIMIT 500
            """,
        )
        for r in records:
            keys = r.get("rel_keys", r.get("relKeys", []))
            result.append(
                {
                    "relationship_type": r.get("rel_type", r.get("relType", "")),
                    "properties": sorted(keys) if keys else [],
                }
            )
        # Deduplicate by rel_type, merge properties
        by_type: dict[str, list[str]] = {}
        for item in result:
            rt = item["relationship_type"]
            if rt not in by_type:
                by_type[rt] = []
            for p in item["properties"]:
                if p not in by_type[rt]:
                    by_type[rt].append(p)
        return [
            {"relationship_type": k, "properties": sorted(v)}
            for k, v in sorted(by_type.items())
        ]
    except Exception:
        return []


def get_node_counts(client: PatientGraphClient, labels: list[str]) -> dict[str, int]:
    """Get count of nodes per label."""
    counts: dict[str, int] = {}
    for label in labels:
        try:
            safe = f"`{label}`" if ":" in label or "-" in label else label
            records = run(client, f"MATCH (n:{safe}) RETURN count(n) AS cnt")
            counts[label] = records[0]["cnt"] if records else 0
        except Exception:
            counts[label] = -1
    return counts


def main() -> dict:
    """Introspect the Patient Graph and return structured schema."""
    client = PatientGraphClient()
    try:
        labels = get_node_labels(client)
        rel_types = get_relationship_types(client)
        node_counts = get_node_counts(client, labels)

        nodes: list[dict] = []
        for label in sorted(labels):
            props = get_node_properties(client, label)
            rels = get_relationships_for_label(client, label)
            nodes.append(
                {
                    "label": label,
                    "count": node_counts.get(label, 0),
                    "properties": props,
                    "relationships": rels,
                }
            )

        rel_properties = get_relationship_properties(client)

        return {
            "node_labels": sorted(labels),
            "relationship_types": sorted(rel_types),
            "nodes": nodes,
            "relationship_properties": rel_properties,
        }
    finally:
        client.close()


if __name__ == "__main__":
    schema = main()
    json.dump(schema, sys.stdout, indent=2)
    sys.stdout.write("\n")
