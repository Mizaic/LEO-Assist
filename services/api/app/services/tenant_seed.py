"""Guardrailed startup seeding for tenant defaults.

Atlas trace:
  DO: DO-72F81432
  DI: DI-96D95459
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-72F81432")

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

from libs.cypher.admin_queries import MERGE_MIZAIC_ORGANIZATION, UPSERT_SYSTEM_CONFIG
from libs.cypher.entra_group_queries import (
    ENSURE_ROLE_IDS,
    ENSURE_USER_LABELS,
    REWRITE_GRANTS_ROLE_TO_HAS_ROLE,
    REWRITE_MEMBER_OF_TO_IS_MEMBER_OF,
)
from libs.neo4j_client.client import PatientGraphClient

_UPSERT_ROLE_AND_GROUP = (
    "MERGE (r:Role {id: $name}) "
    "ON CREATE SET r.name = $name, r.permissions = $perms, r.description = $desc "
    "ON MATCH SET r.name = coalesce(r.name, $name) "
    "MERGE (g:Group {id: $gid}) "
    "ON CREATE SET g.name = $gname, g.source = 'local', "
    "              g.description = $gdesc, g.created_at = datetime() "
    "MERGE (g)-[:HAS_ROLE]->(r)"
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Permissions / roles
# ------------------------------------------------------------------

ALL_PERMISSIONS = [
    # Clinical
    "clinical:view:tasks",
    "clinical:create:referral",
    "clinical:update:triage",
    "clinical:view:assessment",
    "clinical:create:appointment",
    "clinical:view:advice_guidance",
    "clinical:respond:advice_guidance",
    "clinical:manage:pathway",
    "clinical:supervise:referrals",
    "clinical:validate:data",
    "clinical:report:imaging",
    "clinical:qa:imaging",
    "clinical:manage:reception",
    # Support
    "support:view:tickets",
    "support:view:all_tickets",
    "support:create:ticket",
    "support:assign:ticket",
    "support:update:ticket",
    "support:comment:ticket",
    "support:close:ticket",
    "support:delete:ticket",
    "support:view:analytics",
    "support:manage:agents",
    # Regulatory
    "regulatory:view:records",
    "regulatory:decrypt:sensitive",
    "regulatory:audit:access",
    # User
    "user:view:profile",
    "user:update:profile",
    "user:view:preferences",
    "user:update:preferences",
    "user:view:all_users",
    "user:manage:users",
    # LMS
    "lms:view:programs",
    "lms:create:program",
    "lms:update:program",
    "lms:delete:program",
    "lms:view:enrollments",
    "lms:manage:enrollments",
    "lms:view:analytics",
    "lms:create:content",
    "lms:approve:content",
    "lms:create:global_content",
    "lms:approve:global_content",
    "lms:manage:global_system",
    "lms:manage:training_teams",
    # Onboarding
    "onboarding:view:status",
    "onboarding:manage:users",
    "onboarding:configure:technical",
    "onboarding:verify:access",
    # Organisation
    "org:view:details",
    "org:update:details",
    "org:manage:members",
    "org:view:analytics",
    # Admin
    "admin:view:audit_logs",
    "admin:manage:roles",
    "admin:manage:permissions",
    "admin:system:config",
    # SLA
    "sla:view:configuration",
    "sla:view:service",
    "sla:view:all_services",
    "sla:configure:service",
    "sla:configure:organization",
    "sla:approve:service",
    "sla:approve:organization",
    "sla:view:compliance",
    "sla:view:compliance_org",
    "sla:manage:templates",
    # Capacity
    "capacity:view:profile",
    "capacity:view:analytics",
    "capacity:manage:organization",
    "capacity:approve:changes",
    # Organisation (enhanced)
    "organization:manage:settings",
    "organization:view:analytics",
    "organization:manage:users",
    # EDMS
    "edms:view:scheduled_clinic",
    "edms:view:unscheduled_access",
    "edms:view:documents",
    "edms:search:patients",
    "edms:search:break_glass",
    "edms:view:sbar",
    "edms:generate:sbar",
    "edms:view:sbar_citations",
    "edms:click:citation",
    "edms:view:annotations",
    "edms:create:annotations",
    "edms:update:annotations",
    "edms:delete:annotations",
    "edms:export:documents",
    "edms:view:metadata",
    "edms:view:timeline",
    "edms:compare:documents",
    "edms:view:dicom",
    "edms:deeplink:access",
    "edms:view:patient_context",
    "edms:view:audit_logs",
    "edms:search:documents",
    "edms:filter:specialty",
    "edms:filter:category",
    "edms:view:continuous_record",
]

_BASE_USER = [
    "support:create:ticket",
    "user:view:profile",
    "user:update:profile",
    "user:view:preferences",
    "user:update:preferences",
    "org:view:details",
]

DEFAULT_ROLES = [
    # -- Clinical roles -------------------------------------------------------
    {
        "name": "triage_clinician",
        "permissions": [
            "clinical:view:tasks",
            "clinical:update:triage",
            "clinical:view:assessment",
            "clinical:create:appointment",
            "clinical:view:advice_guidance",
            "clinical:respond:advice_guidance",
        ]
        + _BASE_USER,
        "description": "Assess and prioritise patient referrals for the pathway",
    },
    {
        "name": "admin_triage",
        "permissions": [
            "clinical:view:tasks",
            "clinical:update:triage",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Provide administrative support during patient triage",
    },
    {
        "name": "appointment_manual_booking",
        "permissions": [
            "clinical:view:tasks",
            "clinical:create:appointment",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Manually book and manage patient appointments",
    },
    {
        "name": "advice_and_guidance",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:advice_guidance",
            "clinical:respond:advice_guidance",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Advice and Guidance specialist",
    },
    {
        "name": "create_referral",
        "permissions": [
            "clinical:create:referral",
            "clinical:view:tasks",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Create and submit patient referrals",
    },
    {
        "name": "clinician_admin",
        "permissions": [
            "clinical:view:tasks",
            "clinical:update:triage",
            "clinical:view:assessment",
            "clinical:create:appointment",
            "clinical:manage:pathway",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Clinical administration and pathway management",
    },
    {
        "name": "referring_clinician",
        "permissions": [
            "clinical:create:referral",
            "clinical:view:tasks",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Create and manage referrals for patients",
    },
    {
        "name": "receptionist",
        "permissions": [
            "clinical:view:tasks",
            "clinical:create:appointment",
            "clinical:manage:reception",
        ]
        + _BASE_USER,
        "description": "Reception and appointment management",
    },
    {
        "name": "reporting_sonographer",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "clinical:report:imaging",
        ]
        + _BASE_USER,
        "description": "Imaging reporting and diagnostics",
    },
    {
        "name": "sonographer_qa",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "clinical:qa:imaging",
        ]
        + _BASE_USER,
        "description": "Quality assurance for imaging",
    },
    {
        "name": "validation",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "clinical:validate:data",
        ]
        + _BASE_USER,
        "description": "Data validation and verification",
    },
    # -- Operations & management ----------------------------------------------
    {
        "name": "pathway_supervisor",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "clinical:manage:pathway",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Monitor and manage patient pathways across the service",
    },
    {
        "name": "referral_supervisor",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "clinical:supervise:referrals",
            "sla:view:configuration",
            "sla:view:service",
            "sla:configure:service",
            "sla:approve:service",
            "sla:view:compliance",
            "organization:manage:settings",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Oversee referral processing and manage workflow queues",
    },
    {
        "name": "operations_manager",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
            "support:view:all_tickets",
            "support:view:analytics",
            "user:view:all_users",
            "lms:view:programs",
            "lms:view:enrollments",
            "lms:view:analytics",
            "org:view:analytics",
            "admin:view:audit_logs",
        ]
        + _BASE_USER,
        "description": "Operational oversight and analytics",
    },
    # -- Support & compliance -------------------------------------------------
    {
        "name": "support_agent",
        "permissions": [
            "support:view:tickets",
            "support:update:ticket",
            "support:comment:ticket",
            "support:close:ticket",
        ]
        + _BASE_USER,
        "description": "First-line support agent",
    },
    {
        "name": "support_supervisor",
        "permissions": [
            "support:view:tickets",
            "support:view:all_tickets",
            "support:assign:ticket",
            "support:update:ticket",
            "support:comment:ticket",
            "support:close:ticket",
            "support:delete:ticket",
            "support:view:analytics",
            "support:manage:agents",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Support team supervisor",
    },
    {
        "name": "regulatory_reviewer",
        "permissions": [
            "regulatory:view:records",
            "regulatory:decrypt:sensitive",
            "regulatory:audit:access",
            "admin:view:audit_logs",
        ]
        + _BASE_USER,
        "description": "Regulatory compliance and audit access",
    },
    # -- LMS ------------------------------------------------------------------
    {
        "name": "lms_admin",
        "permissions": [
            "lms:view:programs",
            "lms:create:program",
            "lms:update:program",
            "lms:delete:program",
            "lms:view:enrollments",
            "lms:manage:enrollments",
            "lms:view:analytics",
            "lms:create:content",
            "lms:approve:content",
            "lms:create:global_content",
            "lms:approve:global_content",
            "lms:manage:global_system",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Author, approve, and manage all training content and programs",
    },
    {
        "name": "lms_manager",
        "permissions": [
            "lms:view:programs",
            "lms:view:enrollments",
            "lms:manage:enrollments",
            "lms:view:analytics",
            "lms:manage:training_teams",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "Oversee team training and progress",
    },
    {
        "name": "lms_learner",
        "permissions": [
            "lms:view:programs",
            "lms:view:enrollments",
        ]
        + _BASE_USER,
        "description": "Training program learner",
    },
    {
        "name": "lms_training_manager",
        "permissions": [
            "lms:view:programs",
            "lms:view:enrollments",
            "lms:manage:enrollments",
            "lms:view:analytics",
            "lms:manage:training_teams",
            "user:view:all_users",
            "org:view:analytics",
        ]
        + _BASE_USER,
        "description": "LMS training manager (deprecated -- use lms_manager)",
    },
    # -- Onboarding -----------------------------------------------------------
    {
        "name": "customer_onboarding",
        "permissions": [
            "onboarding:view:status",
            "onboarding:manage:users",
            "user:view:all_users",
            "org:manage:members",
        ]
        + _BASE_USER,
        "description": "Customer onboarding and user management",
    },
    {
        "name": "technical_onboarding",
        "permissions": [
            "onboarding:view:status",
            "onboarding:configure:technical",
            "onboarding:verify:access",
            "org:update:details",
        ]
        + _BASE_USER,
        "description": "Technical system setup and validation",
    },
    # -- Admin ----------------------------------------------------------------
    {
        "name": "administrator",
        "permissions": ALL_PERMISSIONS,
        "description": "Full platform access -- manage tenants, users, and settings",
    },
    {
        "name": "organization_administrator",
        "permissions": [
            "org:view:details",
            "org:update:details",
            "org:manage:members",
            "org:view:analytics",
            "organization:manage:settings",
            "organization:view:analytics",
            "organization:manage:users",
            "sla:view:configuration",
            "sla:view:all_services",
            "sla:configure:organization",
            "sla:approve:organization",
            "sla:view:compliance",
            "sla:view:compliance_org",
            "sla:manage:templates",
            "capacity:view:profile",
            "capacity:view:analytics",
            "capacity:manage:organization",
            "capacity:approve:changes",
            "user:view:all_users",
            "user:manage:users",
            "support:view:all_tickets",
            "support:view:analytics",
            "support:create:ticket",
            "lms:view:programs",
            "lms:view:enrollments",
            "lms:view:analytics",
            "admin:view:audit_logs",
            "user:view:profile",
            "user:update:profile",
            "user:view:preferences",
            "user:update:preferences",
        ],
        "description": "Manage users, groups, and settings within your organisation",
    },
    # -- EDMS -----------------------------------------------------------------
    {
        "name": "point_of_care_clinician",
        "permissions": [
            "edms:view:scheduled_clinic",
            "edms:view:documents",
            "edms:view:sbar",
            "edms:view:sbar_citations",
            "edms:click:citation",
            "edms:view:metadata",
            "edms:view:timeline",
            "edms:compare:documents",
            "edms:view:dicom",
            "edms:view:patient_context",
            "edms:search:documents",
            "edms:filter:specialty",
            "edms:filter:category",
            "edms:view:continuous_record",
            "edms:view:annotations",
            "edms:create:annotations",
            "edms:update:annotations",
            "edms:delete:annotations",
            "edms:export:documents",
            "edms:deeplink:access",
        ]
        + _BASE_USER,
        "description": "Scheduled clinic-based document viewing with pre-generated summaries",
    },
    {
        "name": "medical_records_viewer",
        "permissions": [
            "edms:view:unscheduled_access",
            "edms:search:patients",
            "edms:search:break_glass",
            "edms:view:documents",
            "edms:view:sbar",
            "edms:generate:sbar",
            "edms:view:sbar_citations",
            "edms:click:citation",
            "edms:view:metadata",
            "edms:view:timeline",
            "edms:compare:documents",
            "edms:view:dicom",
            "edms:view:patient_context",
            "edms:search:documents",
            "edms:filter:specialty",
            "edms:filter:category",
            "edms:view:continuous_record",
            "edms:view:annotations",
            "edms:create:annotations",
            "edms:update:annotations",
            "edms:delete:annotations",
            "edms:export:documents",
            "edms:deeplink:access",
            "edms:view:audit_logs",
        ]
        + _BASE_USER,
        "description": "Unscheduled reactive document access with break-glass capability",
    },
    # -- Registration ---------------------------------------------------------
    {
        "name": "registration_admin",
        "permissions": [
            "clinical:view:tasks",
            "clinical:view:assessment",
        ]
        + _BASE_USER,
        "description": "Manage patient registration and data quality",
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
    """Idempotent startup seed. Safe to run on every startup."""
    _align_hccp_graph(client)
    _seed_roles(client)
    _seed_system_config(client)
    _seed_mizaic_org_and_group(client)
    _seed_platform_admins(client)
    _seed_prompt_configs(client)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _align_hccp_graph(client: PatientGraphClient) -> None:
    """Add :User labels and rewrite leftover LEO-only relationship names."""
    client.run(ENSURE_USER_LABELS)
    client.run(ENSURE_ROLE_IDS)
    client.run(REWRITE_GRANTS_ROLE_TO_HAS_ROLE)
    client.run(REWRITE_MEMBER_OF_TO_IS_MEMBER_OF)


def _seed_roles(client: PatientGraphClient) -> None:
    for role in DEFAULT_ROLES:
        name = role["name"]
        client.run(
            _UPSERT_ROLE_AND_GROUP,
            name=name,
            perms=role["permissions"],
            desc=role.get("description", ""),
            gid=f"hccp-role-{name}",
            gname=f"HCCP LEO {role.get('description', name)}",
            gdesc=f"Canonical group for role {name}",
        )
    logger.debug("[Tenant] Ensured %d HCCP roles and groups", len(DEFAULT_ROLES))


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
        MERGE_MIZAIC_ORGANIZATION,
        id=MIZAIC_ORG_ID,
        name=MIZAIC_ORG_NAME,
        azureTenantId=(os.getenv("AZURE_AD_TENANT_ID") or "").strip(),
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
    client.run(
        "MATCH (g:Group {id: $gid}), (o:Organization {id: $oid})"
        " MERGE (g)-[:BELONGS_TO]->(o)",
        gid=MIZAIC_GROUP_ID,
        oid=MIZAIC_ORG_ID,
    )
    client.run(
        "MATCH (g:Group {id: $gid}), (r:Role) "
        "WHERE r.id = 'administrator' OR r.name = 'administrator' "
        "MERGE (g)-[:HAS_ROLE]->(r)",
        gid=MIZAIC_GROUP_ID,
    )
    logger.debug("[Tenant] Mizaic org and group upserted")


def _seed_platform_admins(client: PatientGraphClient) -> None:
    """MERGE seed admin users and add them to the Mizaic administrators group.

    User creation is guarded (skip if any already exist) but IS_MEMBER_OF
    edges are always ensured. Platform admins also keep is_platform_admin.
    """
    rows = client.run("MATCH (pr:User) RETURN count(pr) AS cnt")
    existing = rows[0]["cnt"] if rows else 0
    admins = _parse_seed_admins()

    if existing == 0:
        _create_seed_practitioners(client, admins)
    else:
        logger.debug(
            "[Tenant] %d Practitioner(s) already present; skipping create step",
            existing,
        )

    _ensure_platform_admin_edges(client, admins)


def _create_seed_practitioners(
    client: PatientGraphClient,
    admins: list[tuple[str, str]],
) -> None:
    for email, name in admins:
        client.run(
            "MERGE (pr:User {email: $email})"
            " ON CREATE SET pr.id = $id, pr.name = $name,"
            "               pr.is_platform_admin = true, pr.invited_at = datetime()"
            " ON MATCH SET  pr.is_platform_admin = true,"
            "               pr.name = CASE WHEN pr.name IS NULL THEN $name ELSE pr.name END,"
            "               pr.id   = coalesce(pr.id, $id)"
            " SET pr:User",
            email=email,
            name=name,
            id=str(uuid.uuid4()),
        )
        logger.info("[Tenant] Platform admin User seeded: %s", email)


def _ensure_platform_admin_edges(
    client: PatientGraphClient,
    admins: list[tuple[str, str]],
) -> None:
    """Idempotent: add every seed admin to the Mizaic administrators group."""
    for email, _ in admins:
        client.run(
            "MATCH (pr:User {email: $email}), (g:Group {id: $gid})"
            " MERGE (pr)-[:IS_MEMBER_OF]->(g)",
            email=email,
            gid=MIZAIC_GROUP_ID,
        )
        logger.debug("[Tenant] Platform admin group membership ensured: %s", email)


def _seed_prompt_configs(client: PatientGraphClient) -> None:
    """Seed all hardcoded Python prompts into Neo4j as PromptConfig nodes."""
    try:
        rows = client.run("MATCH (p:PromptConfig) RETURN count(p) AS cnt")
        existing = rows[0]["cnt"] if rows else 0
        if existing > 0:
            logger.debug(
                "[Tenant] %d PromptConfig(s) already present; skipping prompt seed",
                existing,
            )
            return
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
        logger.info(
            "[Tenant] PromptConfig nodes seeded (%d prompts)", len(list_prompts())
        )
    except Exception as exc:
        logger.warning("[Tenant] PromptConfig seed failed (non-fatal): %s", exc)
