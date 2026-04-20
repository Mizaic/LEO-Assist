"""Seed canonical roles and Entra-group bindings from a YAML catalogue.

This is the Option-A counterpart to ``scripts/seed_canonical_roles.py``: it
upserts the four canonical LEO roles AND the ``(:Group)-[:GRANTS_ROLE]->(:Role)``
binding catalogue that drives the Entra-group-based RBAC flow.

Idempotent: re-running the script against a populated database only refreshes
``name`` / ``description`` / ``org_id`` on each :Group node and leaves the
:Practitioner-[:HAS_ROLE]->:Role edges untouched (those are written at
sign-in by libs/auth/entra_group_sync.py).

Usage
-----
    python -m scripts.seed_roles_and_groups \\
        --bindings data/identity/entra-group-bindings.yaml

If --bindings is omitted, the script falls back to the .example.yaml file
shipped in the repo so dev environments still get a usable Neo4j catalogue.

Atlas chain: UN-A449F651 -> DI-D9D4BA02 / DI-3610585D
            -> DO-11B1CC4D -> R-A4473229 -> VT-67FB9C97.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from libs.cypher.entra_group_queries import (
    ENTRA_GROUP_OBJECT_ID_CONSTRAINT,
    LIST_ENTRA_GROUP_BINDINGS,
    SEED_GROUP_BINDINGS,
    SEED_ROLE_PERMISSIONS,
)
from libs.cypher.role_queries import CANONICAL_ROLES, SEED_CANONICAL_ROLES
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

DEFAULT_BINDINGS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "identity"
    / "entra-group-bindings.yaml"
)
EXAMPLE_BINDINGS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "identity"
    / "entra-group-bindings.example.yaml"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Bindings YAML not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Bindings YAML must be a mapping at top level: {path}")
    return data


def _validate_bindings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalise binding rows. Raises on malformed input."""
    valid_role_names = set(CANONICAL_ROLES)
    seen_oids: set[str] = set()
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"binding[{idx}] is not a mapping")
        oid = str(row.get("entra_object_id") or "").strip()
        role_name = str(row.get("role_name") or "").strip()
        if not oid:
            raise ValueError(f"binding[{idx}] missing entra_object_id")
        if oid in seen_oids:
            raise ValueError(f"binding[{idx}] duplicate entra_object_id: {oid}")
        if role_name not in valid_role_names:
            raise ValueError(
                f"binding[{idx}] role_name '{role_name}' is not canonical "
                f"(allowed: {sorted(valid_role_names)})"
            )
        seen_oids.add(oid)
        out.append(
            {
                "entra_object_id": oid,
                "name": str(row.get("name") or oid),
                "description": str(row.get("description") or ""),
                "role_name": role_name,
                "org_id": str(row.get("org_id") or ""),
            }
        )
    return out


def _validate_roles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_role_names = set(CANONICAL_ROLES)
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"role[{idx}] is not a mapping")
        name = str(row.get("name") or "").strip()
        if name not in valid_role_names:
            raise ValueError(
                f"role[{idx}] name '{name}' is not canonical "
                f"(allowed: {sorted(valid_role_names)})"
            )
        perms = row.get("permissions") or []
        if not isinstance(perms, list) or not all(isinstance(p, str) for p in perms):
            raise ValueError(f"role[{idx}] permissions must be list[str]")
        out.append(
            {
                "name": name,
                "description": str(row.get("description") or name),
                "permissions": list(perms),
            }
        )
    return out


def seed(
    bindings_path: Path | None = None,
    client: PatientGraphClient | None = None,
) -> dict[str, Any]:
    """Run the full idempotent seed: constraint -> roles -> bindings -> verify.

    Returns a summary dict with counts and the catalogue read back from Neo4j.
    """
    path = bindings_path or DEFAULT_BINDINGS_PATH
    if not path.exists() and path == DEFAULT_BINDINGS_PATH:
        logger.warning(
            "%s not found; falling back to %s (example only)",
            path,
            EXAMPLE_BINDINGS_PATH,
        )
        path = EXAMPLE_BINDINGS_PATH

    payload = _load_yaml(path)
    roles = _validate_roles(list(payload.get("roles") or []))
    bindings = _validate_bindings(list(payload.get("bindings") or []))

    own = client is None
    graph = client or PatientGraphClient()
    try:
        graph.run(ENTRA_GROUP_OBJECT_ID_CONSTRAINT)

        canonical = graph.run(
            SEED_CANONICAL_ROLES, role_names=list(CANONICAL_ROLES)
        )
        seeded_canonical = [r.get("name") for r in canonical if r.get("name")]

        if roles:
            graph.run(SEED_ROLE_PERMISSIONS, roles=roles)

        seeded_bindings: list[dict[str, Any]] = []
        if bindings:
            seeded_bindings = list(
                graph.run(SEED_GROUP_BINDINGS, bindings=bindings)
            )

        catalogue = list(graph.run(LIST_ENTRA_GROUP_BINDINGS))
    finally:
        if own:
            graph.close()

    return {
        "bindings_path": str(path),
        "canonical_roles": seeded_canonical,
        "role_permissions_updated": [r["name"] for r in roles],
        "bindings_seeded": len(seeded_bindings),
        "catalogue": catalogue,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bindings",
        type=Path,
        default=None,
        help=(
            "Path to entra-group-bindings.yaml. Defaults to "
            "data/identity/entra-group-bindings.yaml, falling back to the "
            ".example.yaml shipped in the repo if absent."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        result = seed(bindings_path=args.bindings)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("seed failed: %s", exc)
        return 2

    logger.info(
        "seeded %d canonical role(s); %d Entra-group binding(s) from %s",
        len(result["canonical_roles"]),
        result["bindings_seeded"],
        result["bindings_path"],
    )
    for row in result["catalogue"]:
        logger.info(
            "  %s -> role=%s name=%r org_id=%r",
            row.get("entra_object_id"),
            row.get("role_name"),
            row.get("name"),
            row.get("grant_org_id"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
