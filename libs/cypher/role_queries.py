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
CANONICAL_ROLES: tuple[str, ...] = (
    "clinician",
    "staff",
    "qa_ra_lead",
    "platform_admin",
)

# Seed the four canonical roles. Idempotent.
SEED_CANONICAL_ROLES = """
UNWIND $role_names AS role_name
MERGE (r:Role {name: role_name})
ON CREATE SET r.description = role_name,
              r.permissions = []
RETURN r.name AS name
"""

# Read role state for a practitioner. Returns selected_role (may be null) and
# the distinct set of role names they are allowed to use.
GET_PRACTITIONER_ROLE_STATE = """
MATCH (pr:Practitioner {email: $email})
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(role:Role)
WITH pr, collect(DISTINCT role.name) AS allowed
RETURN pr.selected_role AS selected_role,
       [r IN allowed WHERE r IS NOT NULL] AS allowed_roles
"""

# Write the new selected role. Returns the updated role state. Callers MUST
# validate that the target role is in allowed_roles before calling.
SET_PRACTITIONER_SELECTED_ROLE = """
MATCH (pr:Practitioner {email: $email})
SET pr.selected_role = $role
WITH pr
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(role:Role)
WITH pr, collect(DISTINCT role.name) AS allowed
RETURN pr.selected_role AS selected_role,
       [r IN allowed WHERE r IS NOT NULL] AS allowed_roles
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
