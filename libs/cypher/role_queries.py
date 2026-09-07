"""Cypher queries for the role-first experience (Wave D / DI-LEO-AI-129).

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

These queries read and write the role state used by the UI shell:

- allowed_roles: list of role.name drawn from existing HAS_ROLE edges
- selected_role: single role.name property on the User
- RoleSwitch audit node: append-only record of every role change

Keeping role queries in their own module avoids pushing
``libs/cypher/admin_queries.py`` above the 500 LOC hard limit.
"""

from __future__ import annotations

# Canonical roles. Mirrors services/design-system/src/roles/types.ts.
# These are the HCCP platform roles, kept identical across LEO and HCCP.
# Adding a role here requires a matching entry in:
#   - tenant_seed.py DEFAULT_ROLES (name, permissions, description)
#   - services/design-system/src/roles/types.ts CANONICAL_ROLES + ROLE_COPY
#   - services/design-system/src/roles/navMap.ts
CANONICAL_ROLES: tuple[str, ...] = (
    # Clinical
    "triage_clinician",
    "admin_triage",
    "appointment_manual_booking",
    "advice_and_guidance",
    "create_referral",
    "clinician_admin",
    "referring_clinician",
    "receptionist",
    "reporting_sonographer",
    "sonographer_qa",
    "validation",
    # Operations & management
    "pathway_supervisor",
    "referral_supervisor",
    "operations_manager",
    # Support & compliance
    "support_agent",
    "support_supervisor",
    "regulatory_reviewer",
    # LMS
    "lms_admin",
    "lms_manager",
    "lms_learner",
    "lms_training_manager",
    # Onboarding
    "customer_onboarding",
    "technical_onboarding",
    # Admin
    "administrator",
    "organization_administrator",
    # EDMS
    "point_of_care_clinician",
    "medical_records_viewer",
    # Registration
    "registration_admin",
)

# Seed canonical roles. Idempotent -- ON CREATE SET only so user-edited
# descriptions and permissions are not overwritten.
SEED_CANONICAL_ROLES = """
UNWIND $role_names AS role_name
MERGE (r:Role {id: role_name})
ON CREATE SET r.name = role_name,
              r.description = role_name,
              r.permissions = []
ON MATCH SET r.name = coalesce(r.name, role_name),
             r.id = coalesce(r.id, role_name)
RETURN r.name AS name
"""

# Read role state for a practitioner. Returns selected_role (may be null) and
# the distinct set of role names they are allowed to use.
#
# When pr.is_platform_admin = true, 'administrator' is always included in
# allowed_roles even if no HAS_ROLE edge exists. This prevents platform admins
# from being locked out of the role picker when their HAS_ROLE edge is missing
# (e.g. first login before the Entra sync has run, or seed skipped).
# Read role state for a practitioner.
# Returns selected_role, allowed_roles, and is_platform_admin.
# Python expands allowed_roles to all canonical roles when is_platform_admin
# is true so platform admins can impersonate any role.
GET_PRACTITIONER_ROLE_STATE = """
MATCH (u:User {email: $email})
OPTIONAL MATCH (u)-[:IS_MEMBER_OF]->(g:Group)-[:HAS_ROLE]->(role:Role)
WITH u, collect(DISTINCT coalesce(role.id, role.name)) AS edge_roles
RETURN u.selected_role AS selected_role,
       [r IN edge_roles WHERE r IS NOT NULL] AS allowed_roles,
       coalesce(u.is_platform_admin, false) AS is_platform_admin
"""

# Write the new selected role. Returns the updated role state. Callers MUST
# validate that the target role is in allowed_roles before calling.
# Platform admins bypass this check via role_state.py (all roles allowed).
SET_PRACTITIONER_SELECTED_ROLE = """
MATCH (u:User {email: $email})
SET u.selected_role = $role
WITH u
OPTIONAL MATCH (u)-[:IS_MEMBER_OF]->(g:Group)-[:HAS_ROLE]->(role:Role)
WITH u, collect(DISTINCT coalesce(role.id, role.name)) AS edge_roles
RETURN u.selected_role AS selected_role,
       [r IN edge_roles WHERE r IS NOT NULL] AS allowed_roles,
       coalesce(u.is_platform_admin, false) AS is_platform_admin
"""

# Append-only audit node. One node per successful role switch. Linked to the
# Practitioner so audit queries can reconstruct a user's role history.
CREATE_ROLE_SWITCH_AUDIT = """
MATCH (u:User {email: $email})
CREATE (s:RoleSwitch {
    id: $audit_id,
    from_role: $from_role,
    to_role: $to_role,
    at: datetime($at),
    session_id: $session_id,
    practitioner_email: $email
})
CREATE (u)-[:SWITCHED {at: datetime($at)}]->(s)
RETURN s.id AS id
"""
