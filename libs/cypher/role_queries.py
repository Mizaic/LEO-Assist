"""Cypher queries for the role-first experience (Wave D / DI-LEO-AI-129).

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

These queries read and write the role state used by the UI shell:

- allowed_roles: list of role.name drawn from existing HAS_ROLE edges
- selected_role: single role.name property on the Practitioner
- RoleSwitch audit node: append-only record of every role change

Keeping role queries in their own module avoids pushing
``libs/cypher/admin_queries.py`` above the 500 LOC hard limit.
"""

from __future__ import annotations

# Canonical roles. Mirrors services/design-system/src/roles/types.ts.
# Adding a role here requires a matching entry in:
#   - tenant_seed.py DEFAULT_ROLES (name, permissions, description)
#   - services/design-system/src/roles/types.ts CANONICAL_ROLES + ROLE_COPY
#   - services/design-system/src/roles/navMap.ts
CANONICAL_ROLES: tuple[str, ...] = (
    # Clinical
    "triage_clinician",
    "admin_triage",
    "clinical_coder",
    "auditor",
    # Administration & management
    "appointment_booking",
    "clinical_administrator",
    "referral_supervisor",
    "registration_administrator",
    # System & onboarding
    "pathway_supervisor",
    "org_admin",
    "pipeline_operator",
    "platform_admin",
    # Other / viewer
    "clinical_viewer",
    "read_only",
)

# Seed canonical roles. Idempotent -- ON CREATE SET only so user-edited
# descriptions and permissions are not overwritten.
SEED_CANONICAL_ROLES = """
UNWIND $role_names AS role_name
MERGE (r:Role {name: role_name})
ON CREATE SET r.description = role_name,
              r.permissions = []
RETURN r.name AS name
"""

# Read role state for a practitioner. Returns selected_role (may be null) and
# the distinct set of role names they are allowed to use.
#
# When pr.is_platform_admin = true, 'platform_admin' is always included in
# allowed_roles even if no HAS_ROLE edge exists. This prevents platform admins
# from being locked out of the role picker when their HAS_ROLE edge is missing
# (e.g. first login before the Entra sync has run, or seed skipped).
# Read role state for a practitioner.
# Returns selected_role, allowed_roles, and is_platform_admin.
# Python expands allowed_roles to all canonical roles when is_platform_admin
# is true so platform admins can impersonate any role.
GET_PRACTITIONER_ROLE_STATE = """
MATCH (pr:Practitioner {email: $email})
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(role:Role)
WITH pr, collect(DISTINCT role.name) AS edge_roles
RETURN pr.selected_role AS selected_role,
       [r IN edge_roles WHERE r IS NOT NULL] AS allowed_roles,
       coalesce(pr.is_platform_admin, false) AS is_platform_admin
"""

# Write the new selected role. Returns the updated role state. Callers MUST
# validate that the target role is in allowed_roles before calling.
# Platform admins bypass this check via role_state.py (all roles allowed).
SET_PRACTITIONER_SELECTED_ROLE = """
MATCH (pr:Practitioner {email: $email})
SET pr.selected_role = $role
WITH pr
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(role:Role)
WITH pr, collect(DISTINCT role.name) AS edge_roles
RETURN pr.selected_role AS selected_role,
       [r IN edge_roles WHERE r IS NOT NULL] AS allowed_roles,
       coalesce(pr.is_platform_admin, false) AS is_platform_admin
"""

# Append-only audit node. One node per successful role switch. Linked to the
# Practitioner so audit queries can reconstruct a user's role history.
CREATE_ROLE_SWITCH_AUDIT = """
MATCH (pr:Practitioner {email: $email})
CREATE (s:RoleSwitch {
    id: $audit_id,
    from_role: $from_role,
    to_role: $to_role,
    at: datetime($at),
    session_id: $session_id,
    practitioner_email: $email
})
CREATE (pr)-[:SWITCHED {at: datetime($at)}]->(s)
RETURN s.id AS id
"""
