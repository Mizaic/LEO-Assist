"""Cypher queries for Entra-group-driven role resolution.

Atlas trace:
  DO: DO-F8EFEF89
  DI: DI-E47C3FC2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8EFEF89")

HCCP graph (source of truth -- do not invent a second RBAC model):

    (:User)-[:IS_MEMBER_OF]->(:Group)-[:HAS_ROLE]->(:Role)

A clinician identity node also carries :Practitioner. RBAC queries use :User.
Role nodes carry both ``id`` (HCCP) and ``name`` (LEO) set to the same
canonical role string.

This module never calls Microsoft Graph -- the security DI (DI-3610585D)
forbids it. The overage path explicitly falls through.
"""

from __future__ import annotations

ENTRA_GROUP_OBJECT_ID_CONSTRAINT = """
CREATE CONSTRAINT entra_group_object_id_unique IF NOT EXISTS
FOR (g:Group) REQUIRE g.entra_object_id IS UNIQUE
"""

# Resolve role names from a list of Entra group object IDs. Returns one row
# per matched group with the role name; missing IDs simply do not appear.
RESOLVE_ROLES_FROM_ENTRA_GROUPS = """
UNWIND $group_object_ids AS oid
MATCH (g:Group {entra_object_id: oid})-[:HAS_ROLE]->(r:Role)
RETURN DISTINCT oid AS entra_object_id, coalesce(r.id, r.name) AS role_name
"""

# Drop Entra-backed group memberships that are no longer in the token.
# Local groups (no entra_object_id) are left alone.
DROP_STALE_IS_MEMBER_OF = """
MATCH (u:User {email: $email})-[old:IS_MEMBER_OF]->(g:Group)
WHERE g.entra_object_id IS NOT NULL
  AND NOT g.entra_object_id IN $group_object_ids
DELETE old
RETURN count(old) AS removed
"""

# Ensure the user is a member of every matched Entra group.
ADD_IS_MEMBER_OF = """
MATCH (u:User {email: $email})
WITH u
UNWIND $group_object_ids AS oid
MATCH (g:Group {entra_object_id: oid})
MERGE (u)-[:IS_MEMBER_OF]->(g)
RETURN collect(DISTINCT g.entra_object_id) AS group_ids
"""

# Read allowed roles via the HCCP group path.
READ_ROLES_VIA_GROUPS = """
MATCH (u:User {email: $email})
OPTIONAL MATCH (u)-[:IS_MEMBER_OF]->(g:Group)-[:HAS_ROLE]->(role:Role)
RETURN collect(DISTINCT coalesce(role.id, role.name)) AS allowed_roles
"""

# Idempotent seeder for the Entra-group binding catalogue.
SEED_GROUP_BINDINGS = """
UNWIND $bindings AS b
MERGE (g:Group {entra_object_id: b.entra_object_id})
SET g.name = b.name,
    g.description = b.description,
    g.org_id = coalesce(b.org_id, ''),
    g.entra_tenant_id = coalesce(b.entra_tenant_id, g.entra_tenant_id, ''),
    g.source = 'entra',
    g.updated_at = datetime(),
    g.created_at = coalesce(g.created_at, datetime())
WITH g, b
MERGE (role:Role {id: b.role_name})
SET role.name = coalesce(role.name, b.role_name),
    role.description = coalesce(role.description, b.role_name),
    role.permissions  = coalesce(role.permissions, [])
MERGE (g)-[gr:HAS_ROLE]->(role)
SET gr.org_id = coalesce(b.org_id, '')
RETURN g.entra_object_id AS entra_object_id,
       g.name AS name,
       coalesce(role.id, role.name) AS role_name,
       gr.org_id AS org_id
"""

SEED_ROLE_PERMISSIONS = """
UNWIND $roles AS r
MERGE (role:Role {id: r.name})
SET role.name = r.name,
    role.description = r.description,
    role.permissions = r.permissions
RETURN role.name AS name
"""

LIST_ENTRA_GROUP_BINDINGS = """
MATCH (g:Group)-[gr:HAS_ROLE]->(role:Role)
WHERE g.entra_object_id IS NOT NULL
RETURN g.entra_object_id AS entra_object_id,
       g.name AS name,
       g.description AS description,
       g.org_id AS group_org_id,
       coalesce(role.id, role.name) AS role_name,
       gr.org_id AS grant_org_id
ORDER BY g.name
"""

# One-shot alignment for leftover LEO-only edges / labels.
ENSURE_USER_LABELS = """
MATCH (pr:Practitioner)
WHERE NOT pr:User
SET pr:User
RETURN count(pr) AS updated
"""

ENSURE_ROLE_IDS = """
MATCH (r:Role)
WHERE r.id IS NULL AND r.name IS NOT NULL
SET r.id = r.name
RETURN count(r) AS updated
"""

REWRITE_GRANTS_ROLE_TO_HAS_ROLE = """
MATCH (g:Group)-[old:GRANTS_ROLE]->(r:Role)
MERGE (g)-[:HAS_ROLE]->(r)
DELETE old
RETURN count(old) AS updated
"""

REWRITE_MEMBER_OF_TO_IS_MEMBER_OF = """
MATCH (n)-[old:MEMBER_OF]->(g:Group)
MERGE (n)-[:IS_MEMBER_OF]->(g)
DELETE old
RETURN count(old) AS updated
"""
