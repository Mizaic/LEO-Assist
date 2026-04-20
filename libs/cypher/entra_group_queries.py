"""Cypher queries for Entra-group-driven role resolution.

Implements the Group -> Role binding catalogue used by core-api to translate
Entra (Azure AD) security-group object IDs from the OIDC `groups` claim into
LEO role names. See DI-D9D4BA02 (functional) and DI-3610585D (security) and
the DO-11B1CC4D / R-A4473229 / VT-67FB9C97 chain in Atlas.

Schema additions
----------------
- ``:Group {entra_object_id, name, description, org_id}`` -- mirror of an
  Entra security group. ``entra_object_id`` is the GUID Entra puts in the
  ``groups`` token claim.
- ``(:Group)-[:GRANTS_ROLE {org_id}]->(:Role)`` -- binds an Entra group to
  a LEO role. ``org_id`` is optional and reserved for future per-tenant
  scoping; today it is left empty for global roles.
- Uniqueness: one ``:Group`` per ``entra_object_id``.
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
MATCH (g:Group {entra_object_id: oid})-[:GRANTS_ROLE]->(r:Role)
RETURN DISTINCT oid AS entra_object_id, r.name AS role_name
"""

# Drop any [:HAS_ROLE] edges from the practitioner whose target Role.name is
# not in the supplied $role_names list. Safe to run with an empty list (drops
# every edge). Returns the count of edges removed.
DROP_STALE_HAS_ROLE = """
MATCH (pr:Practitioner {email: $email})-[old:HAS_ROLE]->(stale:Role)
WHERE NOT stale.name IN $role_names
DELETE old
RETURN count(old) AS removed
"""

# Ensure the practitioner has a [:HAS_ROLE] edge to every Role.name in
# $role_names. Roles must already exist (seed script guarantees this).
# Returns the resolved current allowed-role set.
ADD_HAS_ROLE_EDGES = """
MATCH (pr:Practitioner {email: $email})
WITH pr
UNWIND $role_names AS rn
MATCH (role:Role {name: rn})
MERGE (pr)-[:HAS_ROLE]->(role)
RETURN collect(DISTINCT role.name) AS allowed_roles
"""

# Read the current allowed-role set without mutating anything. Used after
# DROP_STALE_HAS_ROLE when the new role set is empty.
READ_HAS_ROLE = """
MATCH (pr:Practitioner {email: $email})
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(role:Role)
RETURN collect(DISTINCT role.name) AS allowed_roles
"""

# Idempotent seeder for the Entra-group binding catalogue. Each row of
# $bindings supplies: entra_object_id, name, description, org_id (optional),
# role_name. The script also seeds the role itself (MERGE) so a binding
# YAML edit + re-run is enough to add a new role-grant.
SEED_GROUP_BINDINGS = """
UNWIND $bindings AS b
MERGE (g:Group {entra_object_id: b.entra_object_id})
SET g.name = b.name,
    g.description = b.description,
    g.org_id = coalesce(b.org_id, ''),
    g.entra_tenant_id = coalesce(b.entra_tenant_id, g.entra_tenant_id, ''),
    g.source = 'entra',
    g.updated_at = datetime()
ON CREATE SET g.created_at = datetime()
WITH g, b
MERGE (role:Role {name: b.role_name})
ON CREATE SET role.description = b.role_name,
              role.permissions = []
MERGE (g)-[gr:GRANTS_ROLE]->(role)
SET gr.org_id = coalesce(b.org_id, '')
RETURN g.entra_object_id AS entra_object_id,
       g.name AS name,
       role.name AS role_name,
       gr.org_id AS org_id
"""

# Seeder for canonical Role permission strings. Idempotent. Run before
# SEED_GROUP_BINDINGS so MERGE on Role above does not overwrite a richer
# permissions list.
SEED_ROLE_PERMISSIONS = """
UNWIND $roles AS r
MERGE (role:Role {name: r.name})
SET role.description = r.description,
    role.permissions = r.permissions
RETURN role.name AS name
"""

# Read-only diagnostic: the current catalogue of Entra group bindings.
LIST_ENTRA_GROUP_BINDINGS = """
MATCH (g:Group)-[gr:GRANTS_ROLE]->(role:Role)
WHERE g.entra_object_id IS NOT NULL
RETURN g.entra_object_id AS entra_object_id,
       g.name AS name,
       g.description AS description,
       g.org_id AS group_org_id,
       role.name AS role_name,
       gr.org_id AS grant_org_id
ORDER BY g.name
"""
