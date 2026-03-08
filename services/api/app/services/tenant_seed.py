"""Guardrailed startup seeding for tenant defaults.

Runs on every startup but each section is idempotent via MERGE / guarded counts.

Seeded items
------------
- Default Role nodes (skipped if any Role exists)
- SystemConfig auth singleton (always upserted)
- Mizaic platform organisation node (MERGE, idempotent)
- Mizaic Platform Admins group (MERGE, idempotent)
- Seed Practitioner nodes listed in SEED_ADMINS (MERGE, idempotent)
"""

from __future__ import annotations

import logging
import os
import uuid

from libs.cypher.admin_queries import UPSERT_SYSTEM_CONFIG
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Permissions / roles
# ------------------------------------------------------------------

ALL_PERMISSIONS = [
    "admin",
    "view_patients",
    "review_coding",
    "run_pipeline",
    "manage_domains",
    "manage_surface_forms",
    "manage_models",
    "view_reports",
    "export_data",
    "view_gold_dataset",
    "configure_auth",
    "manage_users",
    "manage_groups",
    "manage_sub_orgs",
]

DEFAULT_ROLES = [
    {
        "name": "platform_admin",
        "permissions": ALL_PERMISSIONS,
        "description": "Full platform access",
    },
    {
        "name": "org_admin",
        "permissions": [
            "manage_users",
            "manage_groups",
            "manage_sub_orgs",
            "view_reports",
        ],
        "description": "Organisation administrator — manages users, groups, and sub-organisations within their org hierarchy",
    },
    {
        "name": "auditor",
        "permissions": [
            "view_patients",
            "review_coding",
            "view_reports",
            "view_gold_dataset",
        ],
        "description": "View patients, review coding, reports and gold dataset",
    },
    {
        "name": "clinical_coder",
        "permissions": ["view_patients", "review_coding"],
        "description": "GP Practice clinical coder — full access to unredacted patient data and coding review",
    },
    {
        "name": "clinical_viewer",
        "permissions": ["view_patients", "view_reports"],
        "description": "GP Practice clinical viewer — patient data access with redaction applied (set redacted=true on HAS_ROLE)",
    },
    {
        "name": "pipeline_operator",
        "permissions": ["view_patients", "run_pipeline"],
        "description": "View patients and run pipeline",
    },
    {
        "name": "read_only",
        "permissions": ["view_patients", "view_reports"],
        "description": "View patients and reports only",
    },
]

# ------------------------------------------------------------------
# Auth defaults (used only when no SystemConfig exists)
# ------------------------------------------------------------------

DEFAULT_SESSION_TTL_HOURS = 168  # 7 days
DEFAULT_IDLE_TIMEOUT_MINUTES = 30
DEFAULT_COOKIE_SECURE = False
DEFAULT_REQUIRE_MFA = False

# ------------------------------------------------------------------
# Mizaic vendor org / group
# ------------------------------------------------------------------

MIZAIC_ORG_ID = "mizaic-platform"
MIZAIC_ORG_NAME = "Mizaic"
MIZAIC_GROUP_ID = "mizaic-platform-admins"
MIZAIC_GROUP_NAME = "Mizaic Platform Admins"

# Seed admins: read from env (comma-separated emails) or use this default.
# Format: "email:Full Name,email2:Full Name 2"
_SEED_ADMINS_ENV = os.getenv("SEED_PLATFORM_ADMINS", "")
_DEFAULT_ADMINS = [
    ("rob.smith@healthcarecopilot.ai", "Rob Smith"),
]


def _parse_seed_admins() -> list[tuple[str, str]]:
    """Parse SEED_PLATFORM_ADMINS env var into [(email, name), ...]."""
    raw = _SEED_ADMINS_ENV.strip()
    if not raw:
        return _DEFAULT_ADMINS
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            email, name = entry.split(":", 1)
            result.append((email.strip().lower(), name.strip()))
        elif entry:
            result.append((entry.lower(), entry))
    return result or _DEFAULT_ADMINS


# ------------------------------------------------------------------
# Main seed entry point
# ------------------------------------------------------------------


def seed_tenant_defaults(client: PatientGraphClient) -> None:
    """Idempotent startup seed.

    Roles are only seeded once (guard: skip if any Role exists).
    Everything else uses MERGE and is safe to run on every startup.
    """
    _seed_roles(client)
    _seed_system_config(client)
    _seed_mizaic_org_and_group(client)
    _seed_platform_admins(client)
    _seed_prompt_configs(client)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _seed_roles(client: PatientGraphClient) -> None:
    existing_rows = client.run("MATCH (r:Role) RETURN r.name AS name")
    existing_names = {row["name"] for row in (existing_rows or [])}
    new_roles = [r for r in DEFAULT_ROLES if r["name"] not in existing_names]
    if not new_roles:
        logger.debug("[Tenant] All roles already present; skipping role seed")
        return
    logger.info("[Tenant] Seeding %d new roles: %s", len(new_roles), [r["name"] for r in new_roles])
    for role in new_roles:
        client.run(
            "MERGE (r:Role {name: $name})"
            " SET r.permissions = $perms, r.description = $desc",
            name=role["name"],
            perms=role["permissions"],
            desc=role.get("description", ""),
        )


def _seed_system_config(client: PatientGraphClient) -> None:
    existing = client.run("MATCH (sc:SystemConfig {id: 'auth'}) RETURN sc LIMIT 1")
    if existing:
        logger.debug("[Tenant] SystemConfig already present; skipping")
        return
    logger.info("[Tenant] Seeding SystemConfig auth singleton")
    client.run(
        UPSERT_SYSTEM_CONFIG,
        id="auth",
        session_ttl_hours=DEFAULT_SESSION_TTL_HOURS,
        idle_timeout_minutes=DEFAULT_IDLE_TIMEOUT_MINUTES,
        cookie_secure=DEFAULT_COOKIE_SECURE,
        require_mfa=DEFAULT_REQUIRE_MFA,
    )


def _seed_mizaic_org_and_group(client: PatientGraphClient) -> None:
    """MERGE the Mizaic vendor organization and Platform Admins group."""
    client.run(
        "MERGE (o:Organization {id: $id})"
        " ON CREATE SET o.name = $name, o.odsCode = '', o.short_name = 'Mizaic'",
        id=MIZAIC_ORG_ID,
        name=MIZAIC_ORG_NAME,
    )
    client.run(
        "MERGE (g:Group {id: $id})"
        " ON CREATE SET g.name = $name,"
        "               g.description = 'Mizaic vendor platform administrators',"
        "               g.org_id = $org_id,"
        "               g.created_at = datetime()",
        id=MIZAIC_GROUP_ID,
        name=MIZAIC_GROUP_NAME,
        org_id=MIZAIC_ORG_ID,
    )
    # Link group to org
    client.run(
        "MATCH (g:Group {id: $gid}), (o:Organization {id: $oid})"
        " MERGE (g)-[:BELONGS_TO]->(o)",
        gid=MIZAIC_GROUP_ID,
        oid=MIZAIC_ORG_ID,
    )
    logger.debug("[Tenant] Mizaic org and group upserted")


def _seed_platform_admins(client: PatientGraphClient) -> None:
    """MERGE seed admin Practitioners, assign platform_admin role, add to Mizaic group."""
    admins = _parse_seed_admins()
    for email, name in admins:
        client.run(
            "MERGE (pr:Practitioner {email: $email})"
            " ON CREATE SET pr.id = $id, pr.name = $name,"
            "               pr.is_platform_admin = true, pr.invited_at = datetime()"
            " ON MATCH SET  pr.is_platform_admin = true,"
            "               pr.name = CASE WHEN pr.name IS NULL THEN $name ELSE pr.name END,"
            "               pr.id   = coalesce(pr.id, $id)",
            email=email,
            name=name,
            id=str(uuid.uuid4()),
        )
        # Assign platform_admin role (idempotent MERGE)
        client.run(
            "MATCH (pr:Practitioner {email: $email}), (r:Role {name: 'platform_admin'})"
            " MERGE (pr)-[rel:HAS_ROLE]->(r)"
            " ON CREATE SET rel.org_id = ''",
            email=email,
        )
        # Add to Mizaic Platform Admins group (idempotent MERGE)
        client.run(
            "MATCH (pr:Practitioner {email: $email}), (g:Group {id: $gid})"
            " MERGE (pr)-[:MEMBER_OF]->(g)",
            email=email,
            gid=MIZAIC_GROUP_ID,
        )
        logger.info("[Tenant] Platform admin seeded: %s", email)


def _seed_prompt_configs(client: PatientGraphClient) -> None:
    """Seed all hardcoded Python prompts into Neo4j as PromptConfig nodes."""
    try:
        from libs.cypher.prompt_config_queries import UPSERT_SEED_PROMPT
        from libs.prompts.registry import list_prompts, _REGISTRY

        for name, version in list_prompts():
            text = _REGISTRY.get((name, version), "")
            if not text:
                continue
            client.run(
                UPSERT_SEED_PROMPT,
                id=str(uuid.uuid4()),
                name=name,
                version=version,
                description="",
                system_prompt=text,
                output_schema="{}",
                verification=False,
                few_shot_examples="[]",
                max_few_shot=10,
            )
        logger.info("[Tenant] PromptConfig nodes seeded (%d prompts)", len(list_prompts()))
    except Exception as exc:
        logger.warning("[Tenant] PromptConfig seed failed (non-fatal): %s", exc)
