#!/usr/bin/env python3
"""Seed Practitioner nodes for MVP tenant access.

Creates Practitioner nodes and links them to Organization nodes via WORKS_AT.

Usage:
    python -m scripts.seed_practitioners [--list-orgs]

Flags:
    --list-orgs   Just print all Organization nodes and exit.

Only seeds when no Practitioner nodes exist; skips if any are already present
to avoid overwriting user-modified practitioners.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

# Load secrets
secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets", ".env")
load_dotenv(secrets_path)

from libs.neo4j_client.client import PatientGraphClient


def list_organizations(client: PatientGraphClient) -> list[dict]:
    """List all Organization nodes in the Patient Graph."""
    return client.run(
        "MATCH (o:Organization) "
        "RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, "
        "       o.short_name AS short_name "
        "ORDER BY o.name"
    )


def seed_practitioner(
    client: PatientGraphClient,
    *,
    email: str,
    name: str,
    is_platform_admin: bool = False,
    org_names: list[str] | None = None,
) -> None:
    """Create or update a Practitioner and link to organizations."""
    from uuid import uuid4

    email = email.lower().strip()

    client.run(
        "MERGE (pr:Practitioner {email: $email}) "
        "SET pr.name = $name, "
        "    pr.is_platform_admin = $is_admin, "
        "    pr.updated_at = datetime(), "
        "    pr.id = coalesce(pr.id, $new_id)",
        email=email,
        name=name,
        is_admin=is_platform_admin,
        new_id=str(uuid4()),
    )
    print(f"  [OK] Practitioner: {name} <{email}> (admin={is_platform_admin})")

    if org_names:
        for org_name in org_names:
            rows = client.run(
                "MATCH (pr:Practitioner {email: $email}) "
                "MATCH (o:Organization) WHERE toLower(o.name) CONTAINS toLower($org_name) "
                "MERGE (pr)-[:WORKS_AT]->(o) "
                "RETURN o.name AS matched_name",
                email=email,
                org_name=org_name,
            )
            if rows:
                print(f"       -> linked to: {rows[0]['matched_name']}")
            else:
                print(f"       [WARN] No organization matching '{org_name}' found")


def main():
    client = PatientGraphClient()
    try:
        if "--list-orgs" in sys.argv:
            print("=" * 70)
            print("ORGANIZATIONS IN PATIENT GRAPH")
            print("=" * 70)
            orgs = list_organizations(client)
            if not orgs:
                print("  (none found)")
            for o in orgs:
                ods = o.get("odsCode") or ""
                short = o.get("short_name") or ""
                print(f"  {o['name']}")
                print(f"    ID: {o['id']}  ODS: {ods}  Short: {short}")
            print(f"\nTotal: {len(orgs)} organizations")
            return

        practitioners = client.run("MATCH (pr:Practitioner) RETURN count(pr) AS cnt")
        existing = practitioners[0]["cnt"] if practitioners else 0
        if existing > 0:
            print(f"Skipped — {existing} Practitioner(s) already present.")
            return

        print("=" * 70)
        print("SEEDING PRACTITIONERS")
        print("=" * 70)

        # Rob Smith - platform admin, sees all organizations
        seed_practitioner(
            client,
            email="rob.smith@healthcarecopilot.ai",
            name="Rob Smith",
            is_platform_admin=True,
        )

        # Ben Noble - standard user, WOODBROOK MEDICAL CENTRE only
        seed_practitioner(
            client,
            email="ben.noble@nhs.net",
            name="Ben Noble",
            is_platform_admin=False,
            org_names=["WOODBROOK"],
        )

        print("\n" + "=" * 70)
        print("DONE")
        print("=" * 70)

    finally:
        client.close()


if __name__ == "__main__":
    main()
