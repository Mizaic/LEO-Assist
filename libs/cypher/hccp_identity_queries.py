"""HCCP identity and admin RBAC Cypher.

Atlas trace:
  DO: DO-308DD1A6
  DI: DI-D49BCE55

HCCP graph: (:User)-[:IS_MEMBER_OF]->(:Group)-[:HAS_ROLE]->(:Role)

A clinician also carries :Practitioner on the same node. Clinical queries
stay on :Practitioner. Admin and RBAC queries use :User.
"""

# ------------------------------------------------------------------
# Practitioners
# ------------------------------------------------------------------

LIST_PRACTITIONERS = """
MATCH (pr:User)
WHERE (pr.deactivated IS NULL OR pr.deactivated = false)
OPTIONAL MATCH (pr)-[:WORKS_AT]->(o)
WITH pr, collect(DISTINCT o.id) AS org_ids, collect(DISTINCT o.name) AS org_names
OPTIONAL MATCH (pr)-[:IS_MEMBER_OF]->(g:Group)
OPTIONAL MATCH (g)-[:HAS_ROLE]->(role:Role)
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(legacy:Role)
WITH pr, org_ids, org_names,
     collect(DISTINCT CASE WHEN g IS NULL THEN NULL
       ELSE {id: g.id, name: g.name} END) AS raw_groups,
     collect(DISTINCT CASE WHEN role IS NULL THEN NULL
       ELSE {
         role: coalesce(role.id, role.name),
         org_id: coalesce(g.org_id, '')
       } END) AS raw_roles,
     collect(DISTINCT coalesce(legacy.id, legacy.name)) AS raw_legacy
WITH pr, org_ids, org_names,
     [x IN raw_groups WHERE x IS NOT NULL] AS groups,
     [x IN raw_roles WHERE x IS NOT NULL] AS roles,
     [x IN raw_legacy WHERE x IS NOT NULL] AS legacy_roles
RETURN pr.id AS id, pr.email AS email, pr.name AS name,
       pr.is_platform_admin AS is_platform_admin,
       pr.last_seen_at AS last_seen_at, pr.invited_at AS invited_at,
       org_ids, org_names, roles, groups, legacy_roles
ORDER BY pr.email
"""

LIST_PRACTITIONERS_SCOPED = """
MATCH (pr:User)
WHERE (pr.deactivated IS NULL OR pr.deactivated = false)
OPTIONAL MATCH (pr)-[:WORKS_AT]->(o)
WITH pr, collect(DISTINCT o.id) AS org_ids, collect(DISTINCT o.name) AS org_names
WHERE any(oid IN org_ids WHERE oid IN $scope_org_ids)
OPTIONAL MATCH (pr)-[:IS_MEMBER_OF]->(g:Group)
OPTIONAL MATCH (g)-[:HAS_ROLE]->(role:Role)
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(legacy:Role)
WITH pr, org_ids, org_names,
     collect(DISTINCT CASE WHEN g IS NULL THEN NULL
       ELSE {id: g.id, name: g.name} END) AS raw_groups,
     collect(DISTINCT CASE WHEN role IS NULL THEN NULL
       ELSE {
         role: coalesce(role.id, role.name),
         org_id: coalesce(g.org_id, '')
       } END) AS raw_roles,
     collect(DISTINCT coalesce(legacy.id, legacy.name)) AS raw_legacy
WITH pr, org_ids, org_names,
     [x IN raw_groups WHERE x IS NOT NULL] AS groups,
     [x IN raw_roles WHERE x IS NOT NULL] AS roles,
     [x IN raw_legacy WHERE x IS NOT NULL] AS legacy_roles
RETURN pr.id AS id, pr.email AS email, pr.name AS name,
       pr.is_platform_admin AS is_platform_admin,
       pr.last_seen_at AS last_seen_at, pr.invited_at AS invited_at,
       org_ids, org_names, roles, groups, legacy_roles
ORDER BY pr.email
"""

LIST_GROUPS_SCOPED = """
MATCH (g:Group)
WHERE g.org_id IN $scope_org_ids
OPTIONAL MATCH (g)-[:BELONGS_TO]->(o)
OPTIONAL MATCH (g)<-[:IS_MEMBER_OF]-(pr:User)
WITH g, o.id AS org_id, o.name AS org_name, count(pr) AS member_count
RETURN g.id AS id, g.name AS name, g.description AS description,
       g.org_id AS org_id, org_name, member_count, g.created_at AS created_at,
       coalesce(g.source, 'local') AS source,
       g.entra_object_id AS entra_object_id,
       g.entra_tenant_id AS entra_tenant_id
ORDER BY g.name
"""

CREATE_PRACTITIONER = """
MERGE (pr:Practitioner:User {email: $email})
SET pr:User, pr:Practitioner,
    pr.name = $name, pr.is_platform_admin = $is_platform_admin,
    pr.id = coalesce(pr.id, $id), pr.invited_at = datetime()
WITH pr
UNWIND $org_ids AS org_id
OPTIONAL MATCH (o) WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance
    OR o:ServiceProvider OR o:Organization) AND o.id = org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pr)-[:WORKS_AT]->(o)
)
RETURN pr.email AS email
"""

UPDATE_PRACTITIONER = """
MATCH (pr:User {email: $email})
SET pr += $updates
WITH pr
OPTIONAL MATCH (pr)-[w:WORKS_AT]->()
DELETE w
WITH pr
UNWIND $org_ids AS org_id
OPTIONAL MATCH (o) WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance
    OR o:ServiceProvider OR o:Organization) AND o.id = org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pr)-[:WORKS_AT]->(o)
)
RETURN pr.email AS email
"""

GET_PRACTITIONER_ORG_IDS = """
MATCH (pr:User {email: $email})-[:WORKS_AT]->(o)
RETURN collect(o.id) AS org_ids
"""

LIST_ORG_PRACTITIONERS = """
MATCH (pr:User)-[:WORKS_AT]->(o)
WHERE o.id = $org_id
  AND (pr.deactivated IS NULL OR pr.deactivated = false)
OPTIONAL MATCH (pr)-[:IS_MEMBER_OF]->(g:Group)
OPTIONAL MATCH (g)-[:HAS_ROLE]->(role:Role)
WHERE coalesce(g.org_id, '') IN [$org_id, '']
OPTIONAL MATCH (pr)-[:HAS_ROLE]->(legacy:Role)
WITH pr,
     collect(DISTINCT CASE WHEN g IS NULL THEN NULL
       ELSE {id: g.id, name: g.name} END) AS raw_groups,
     collect(DISTINCT CASE WHEN role IS NULL THEN NULL
       ELSE {
         role: coalesce(role.id, role.name),
         org_id: coalesce(g.org_id, '')
       } END) AS raw_roles,
     collect(DISTINCT coalesce(legacy.id, legacy.name)) AS raw_legacy
WITH pr,
     [x IN raw_groups WHERE x IS NOT NULL] AS groups,
     [x IN raw_roles WHERE x IS NOT NULL] AS roles,
     [x IN raw_legacy WHERE x IS NOT NULL] AS legacy_roles
RETURN pr.id AS id, pr.email AS email, pr.name AS name,
       pr.is_platform_admin AS is_platform_admin,
       pr.last_seen_at AS last_seen_at, pr.invited_at AS invited_at,
       roles, groups, legacy_roles
ORDER BY pr.email
"""

ADD_PRACTITIONER_TO_ORG = """
MATCH (pr:User {email: $email})
MATCH (o) WHERE o.id = $org_id
MERGE (pr)-[:WORKS_AT]->(o)
RETURN pr.email AS email
"""

REMOVE_PRACTITIONER_FROM_ORG = """
MATCH (pr:User {email: $email})-[w:WORKS_AT]->(o)
WHERE o.id = $org_id
DELETE w
RETURN pr.email AS email
"""

SET_USER_GROUPS = """
MATCH (u:User {email: $email})
OPTIONAL MATCH (u)-[m:IS_MEMBER_OF]->(:Group)
DELETE m
WITH DISTINCT u
WITH u, CASE WHEN size($group_ids) = 0 THEN [null] ELSE $group_ids END AS gids
UNWIND gids AS gid
OPTIONAL MATCH (g:Group {id: gid})
FOREACH (_ IN CASE WHEN g IS NOT NULL THEN [1] ELSE [] END |
  MERGE (u)-[:IS_MEMBER_OF]->(g)
)
RETURN u.email AS email
"""

CLEAR_LEGACY_USER_ROLES = """
MATCH (u:User {email: $email})-[r:HAS_ROLE]->(:Role)
DELETE r
RETURN count(r) AS removed
"""

DEACTIVATE_PRACTITIONER = """
MATCH (pr:User {email: $email})
SET pr.deactivated = true
OPTIONAL MATCH (pr)-[r:HAS_ROLE]->()
DELETE r
OPTIONAL MATCH (pr)-[m:IS_MEMBER_OF]->()
DELETE m
OPTIONAL MATCH (pr)-[w:WORKS_AT]->()
DELETE w
RETURN pr.email AS email
"""

UPDATE_PRACTITIONER_LAST_SEEN = """
MATCH (pr:User {email: $email})
SET pr.last_seen_at = datetime()
RETURN pr.email AS email
"""

# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------

LIST_GROUPS = """
MATCH (g:Group)
OPTIONAL MATCH (g)-[:BELONGS_TO]->(o)
OPTIONAL MATCH (g)<-[:IS_MEMBER_OF]-(pr:User)
WITH g, o.id AS org_id, o.name AS org_name, count(pr) AS member_count
RETURN g.id AS id, g.name AS name, g.description AS description,
       g.org_id AS org_id, org_name, member_count, g.created_at AS created_at,
       coalesce(g.source, 'local') AS source,
       g.entra_object_id AS entra_object_id,
       g.entra_tenant_id AS entra_tenant_id
ORDER BY g.name
"""

CREATE_GROUP = """
CREATE (g:Group)
SET g.id = $id, g.name = $name, g.description = $description,
    g.org_id = $org_id, g.source = coalesce($source, 'local'),
    g.created_at = datetime()
WITH g
OPTIONAL MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization)
  AND o.id = $org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (g)-[:BELONGS_TO]->(o)
)
RETURN g.id AS id
"""

# Backfill any pre-existing :Group rows that lack a `source` property to
# `source='local'`. Run before opening up the new /admin/entra/* router so
# the dual local/Entra model has clean defaults. Idempotent: re-running on
# an already-backfilled database returns 0.
BACKFILL_GROUP_SOURCE_LOCAL = """
MATCH (g:Group)
WHERE g.source IS NULL
SET g.source = 'local'
RETURN count(g) AS updated
"""

# Upsert a shadow `:Group` node that mirrors an Entra security group. Used
# by `/admin/entra/groups` after a successful Microsoft Graph create/import
# so the binding catalogue (`(:Group {entra_object_id})-[:HAS_ROLE]->`)
# can be populated by `/admin/entra/groups/{id}/bind`.
UPSERT_ENTRA_SHADOW_GROUP = """
MERGE (g:Group {entra_object_id: $entra_object_id})
SET g.name = $name,
    g.description = coalesce($description, ''),
    g.entra_tenant_id = $entra_tenant_id,
    g.source = 'entra',
    g.org_id = coalesce($org_id, ''),
    g.updated_at = datetime()
ON CREATE SET g.created_at = datetime(),
              g.id = coalesce(g.id, $entra_object_id)
RETURN g.entra_object_id AS entra_object_id,
       g.id AS id,
       g.name AS name,
       g.description AS description,
       g.entra_tenant_id AS entra_tenant_id,
       g.source AS source
"""

# Read a single :Group by Entra object id, including any [:HAS_ROLE]
# edge it currently carries. Used by the bind endpoint to report what role
# (if any) is already attached.
GET_ENTRA_SHADOW_GROUP = """
MATCH (g:Group {entra_object_id: $entra_object_id})
OPTIONAL MATCH (g)-[gr:HAS_ROLE]->(role:Role)
RETURN g.entra_object_id AS entra_object_id,
       g.name AS name,
       g.entra_tenant_id AS entra_tenant_id,
       g.source AS source,
       collect(DISTINCT coalesce(role.id, role.name)) AS role_names
"""

# Bind an existing shadow :Group {entra_object_id} to a :Role by name.
# The :Role must exist (seeded by scripts/seed_roles_and_groups.py). The
# optional `org_id` scopes the grant to a specific organisation; pass an
# empty string for a global grant.
BIND_ENTRA_GROUP_TO_ROLE = """
MATCH (g:Group {entra_object_id: $entra_object_id})
MATCH (role:Role)
WHERE role.id = $role_name OR role.name = $role_name
MERGE (g)-[gr:HAS_ROLE]->(role)
SET gr.org_id = coalesce($org_id, '')
RETURN g.entra_object_id AS entra_object_id,
       coalesce(role.id, role.name) AS role_name,
       gr.org_id AS org_id
"""

# Drop a single [:HAS_ROLE] edge between a shadow :Group and a :Role.
UNBIND_ENTRA_GROUP_ROLE = """
MATCH (g:Group {entra_object_id: $entra_object_id})-[gr:HAS_ROLE]->(role:Role)
WHERE role.id = $role_name OR role.name = $role_name
DELETE gr
RETURN count(gr) AS removed
"""

UPDATE_GROUP = """
MATCH (g:Group {id: $id})
SET g += $updates
RETURN g.id AS id
"""

DELETE_GROUP = """
MATCH (g:Group {id: $id})
OPTIONAL MATCH (g)<-[m:IS_MEMBER_OF]-()
DELETE m
DETACH DELETE g
RETURN count(*) AS deleted
"""

LIST_GROUP_MEMBERS = """
MATCH (g:Group {id: $id})<-[:IS_MEMBER_OF]-(pr:User)
RETURN pr.email AS email, pr.name AS name
ORDER BY pr.email
"""

ADD_GROUP_MEMBER = """
MATCH (g:Group {id: $group_id})
MATCH (pr:User {email: $email})
MERGE (pr)-[:IS_MEMBER_OF]->(g)
RETURN pr.email AS email
"""

REMOVE_GROUP_MEMBER = """
MATCH (g:Group {id: $group_id})<-[m:IS_MEMBER_OF]-(pr:User {email: $email})
DELETE m
RETURN pr.email AS email
"""

# ------------------------------------------------------------------
# Roles
# ------------------------------------------------------------------

LIST_ROLES = """
MATCH (r:Role)
RETURN r.name AS name, r.permissions AS permissions, r.description AS description
ORDER BY r.name
"""

GET_ROLE = """
MATCH (r:Role {name: $name})
RETURN r.name AS name, r.permissions AS permissions, r.description AS description
"""

# ------------------------------------------------------------------
# User roles -- HCCP path: User-[:IS_MEMBER_OF]->Group-[:HAS_ROLE]->Role
# ------------------------------------------------------------------

LIST_USER_ROLES = """
MATCH (u:User {email: $email})-[:IS_MEMBER_OF]->(g:Group)-[:HAS_ROLE]->(role:Role)
RETURN coalesce(role.id, role.name) AS role, coalesce(g.org_id, '') AS org_id
"""

ASSIGN_USER_ROLE = """
MATCH (u:User {email: $email})
MATCH (role:Role)
WHERE role.id = $role_name OR role.name = $role_name
MATCH (g:Group)-[:HAS_ROLE]->(role)
WHERE $org_id = '' OR coalesce(g.org_id, '') IN [$org_id, '']
WITH u, role, g
ORDER BY CASE WHEN coalesce(g.org_id, '') = $org_id THEN 0 ELSE 1 END
LIMIT 1
MERGE (u)-[:IS_MEMBER_OF]->(g)
RETURN coalesce(role.id, role.name) AS role
"""

REMOVE_USER_ROLE = """
MATCH (u:User {email: $email})-[m:IS_MEMBER_OF]->(g:Group)-[:HAS_ROLE]->(role:Role)
WHERE role.id = $role_name OR role.name = $role_name
DELETE m
RETURN coalesce(role.id, role.name) AS role
"""
