"""Cypher queries for admin/tenant management.

Organisations, practitioners, groups, roles, and system config.
"""

# ------------------------------------------------------------------
# Organisations
# ------------------------------------------------------------------

LIST_ORGS = """
MATCH (o)
WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization
OPTIONAL MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
WHERE (gp.id = o.id)
   OR (gp)-[:COMMISSIONED_BY]->(o)
   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(o)
WITH o, count(DISTINCT p) AS patient_count
OPTIONAL MATCH (o)-[:COMMISSIONED_BY]->(parent)
OPTIONAL MATCH (o)-[:PART_OF_ALLIANCE]->(alliance)
RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, o.short_name AS short_name,
       labels(o) AS labels, patient_count,
       parent.id AS parent_id, parent.name AS parent_name,
       alliance.id AS alliance_id, alliance.name AS alliance_name,
       CASE
         WHEN 'GPPractice'    IN labels(o) THEN 'gp'
         WHEN 'ICB'           IN labels(o) THEN 'icb'
         WHEN 'CancerAlliance' IN labels(o) THEN 'alliance'
         WHEN parent IS NOT NULL            THEN 'gp'
         WHEN alliance IS NOT NULL          THEN 'icb'
         ELSE 'organization'
       END AS org_type
ORDER BY o.name
"""

CREATE_ORG_GP = """
CREATE (o:GPPractice:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name
RETURN o.id AS id
"""

CREATE_ORG_ICB = """
CREATE (o:ICB:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name
RETURN o.id AS id
"""

CREATE_ORG_ALLIANCE = """
CREATE (o:CancerAlliance:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name
RETURN o.id AS id
"""

UPDATE_ORG = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization) AND o.id = $id
SET o += $updates
RETURN o.id AS id
"""

DELETE_ORG = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization) AND o.id = $id
OPTIONAL MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
WHERE gp.id = o.id OR (gp)-[:COMMISSIONED_BY]->(o) OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(o)
WITH o, count(DISTINCT p) AS patient_count
WHERE patient_count = 0
WITH collect(o) AS nodes
UNWIND nodes AS n
DETACH DELETE n
WITH nodes
RETURN size(nodes) AS deleted
LIMIT 1
"""

LINK_ORG_COMMISSIONED_BY = """
MATCH (child), (parent)
WHERE (child:GPPractice OR child:Organization) AND child.id = $child_id
  AND (parent:ICB OR parent:Organization) AND parent.id = $parent_id
MERGE (child)-[:COMMISSIONED_BY]->(parent)
RETURN child.id AS id
"""

LINK_ORG_PART_OF_ALLIANCE = """
MATCH (icb:ICB), (alliance:CancerAlliance)
WHERE icb.id = $icb_id AND alliance.id = $alliance_id
MERGE (icb)-[:PART_OF_ALLIANCE]->(alliance)
RETURN icb.id AS id
"""

# ------------------------------------------------------------------
# Practitioners
# ------------------------------------------------------------------

LIST_PRACTITIONERS = """
MATCH (pr:Practitioner)
WHERE (pr.deactivated IS NULL OR pr.deactivated = false)
OPTIONAL MATCH (pr)-[:WORKS_AT]->(o)
WITH pr, collect(DISTINCT o.id) AS org_ids, collect(DISTINCT o.name) AS org_names
OPTIONAL MATCH (pr)-[r:HAS_ROLE]->(role:Role)
WITH pr, org_ids, org_names, collect(DISTINCT {role: role.name, org_id: r.org_id}) AS roles
RETURN pr.id AS id, pr.email AS email, pr.name AS name,
       pr.is_platform_admin AS is_platform_admin,
       pr.last_seen_at AS last_seen_at, pr.invited_at AS invited_at,
       org_ids, org_names, roles
ORDER BY pr.email
"""

CREATE_PRACTITIONER = """
MERGE (pr:Practitioner {email: $email})
SET pr.name = $name, pr.is_platform_admin = $is_platform_admin,
    pr.id = coalesce(pr.id, $id), pr.invited_at = datetime()
WITH pr
UNWIND $org_ids AS org_id
OPTIONAL MATCH (o) WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization) AND o.id = org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pr)-[:WORKS_AT]->(o)
)
RETURN pr.email AS email
"""

UPDATE_PRACTITIONER = """
MATCH (pr:Practitioner {email: $email})
SET pr += $updates
WITH pr
OPTIONAL MATCH (pr)-[w:WORKS_AT]->()
DELETE w
WITH pr
UNWIND $org_ids AS org_id
OPTIONAL MATCH (o) WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization) AND o.id = org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pr)-[:WORKS_AT]->(o)
)
RETURN pr.email AS email
"""

GET_PRACTITIONER_ORG_IDS = """
MATCH (pr:Practitioner {email: $email})-[:WORKS_AT]->(o)
RETURN collect(o.id) AS org_ids
"""

DEACTIVATE_PRACTITIONER = """
MATCH (pr:Practitioner {email: $email})
SET pr.deactivated = true
OPTIONAL MATCH (pr)-[r:HAS_ROLE]->()
DELETE r
OPTIONAL MATCH (pr)-[m:MEMBER_OF]->()
DELETE m
OPTIONAL MATCH (pr)-[w:WORKS_AT]->()
DELETE w
RETURN pr.email AS email
"""

UPDATE_PRACTITIONER_LAST_SEEN = """
MATCH (pr:Practitioner {email: $email})
SET pr.last_seen_at = datetime()
RETURN pr.email AS email
"""

# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------

LIST_GROUPS = """
MATCH (g:Group)
OPTIONAL MATCH (g)-[:BELONGS_TO]->(o)
OPTIONAL MATCH (g)<-[:MEMBER_OF]-(pr:Practitioner)
WITH g, o.id AS org_id, o.name AS org_name, count(pr) AS member_count
RETURN g.id AS id, g.name AS name, g.description AS description,
       g.org_id AS org_id, org_name, member_count, g.created_at AS created_at
ORDER BY g.name
"""

CREATE_GROUP = """
CREATE (g:Group)
SET g.id = $id, g.name = $name, g.description = $description,
    g.org_id = $org_id, g.created_at = datetime()
WITH g
OPTIONAL MATCH (o) WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:Organization) AND o.id = $org_id
FOREACH (_ IN CASE WHEN o IS NOT NULL THEN [1] ELSE [] END |
  MERGE (g)-[:BELONGS_TO]->(o)
)
RETURN g.id AS id
"""

UPDATE_GROUP = """
MATCH (g:Group {id: $id})
SET g += $updates
RETURN g.id AS id
"""

DELETE_GROUP = """
MATCH (g:Group {id: $id})
OPTIONAL MATCH (g)<-[m:MEMBER_OF]-()
DELETE m
DETACH DELETE g
RETURN count(*) AS deleted
"""

LIST_GROUP_MEMBERS = """
MATCH (g:Group {id: $id})<-[:MEMBER_OF]-(pr:Practitioner)
RETURN pr.email AS email, pr.name AS name
ORDER BY pr.email
"""

ADD_GROUP_MEMBER = """
MATCH (g:Group {id: $group_id})
MATCH (pr:Practitioner {email: $email})
MERGE (pr)-[:MEMBER_OF]->(g)
RETURN pr.email AS email
"""

REMOVE_GROUP_MEMBER = """
MATCH (g:Group {id: $group_id})<-[m:MEMBER_OF]-(pr:Practitioner {email: $email})
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
# User roles (HAS_ROLE relationship with optional org_id)
# ------------------------------------------------------------------

LIST_USER_ROLES = """
MATCH (pr:Practitioner {email: $email})-[r:HAS_ROLE]->(role:Role)
RETURN role.name AS role, r.org_id AS org_id
"""

ASSIGN_USER_ROLE = """
MATCH (pr:Practitioner {email: $email})
MATCH (role:Role {name: $role_name})
MERGE (pr)-[r:HAS_ROLE]->(role)
SET r.org_id = $org_id
RETURN role.name AS role
"""

REMOVE_USER_ROLE = """
MATCH (pr:Practitioner {email: $email})-[r:HAS_ROLE]->(role:Role {name: $role_name})
DELETE r
RETURN role.name AS role
"""

# ------------------------------------------------------------------
# System config
# ------------------------------------------------------------------

GET_SYSTEM_CONFIG = """
MATCH (sc:SystemConfig {id: $id})
RETURN sc.session_ttl_hours AS session_ttl_hours,
       sc.idle_timeout_minutes AS idle_timeout_minutes,
       sc.cookie_secure AS cookie_secure,
       sc.require_mfa AS require_mfa
"""

UPSERT_SYSTEM_CONFIG = """
MERGE (sc:SystemConfig {id: $id})
SET sc.session_ttl_hours = $session_ttl_hours,
    sc.idle_timeout_minutes = $idle_timeout_minutes,
    sc.cookie_secure = $cookie_secure,
    sc.require_mfa = $require_mfa
RETURN sc.id AS id
"""
