"""Cypher queries for admin/tenant management.

Atlas trace:
  DO: DO-72F81432
  DI: DI-96D95459
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-72F81432")

Organisations, practitioners, groups, roles, and system config.
Identity and RBAC query strings live in hccp_identity_queries.py.
"""

from libs.cypher.hccp_identity_queries import (  # noqa: F401
    ADD_GROUP_MEMBER,
    ADD_PRACTITIONER_TO_ORG,
    ASSIGN_USER_ROLE,
    BACKFILL_GROUP_SOURCE_LOCAL,
    BIND_ENTRA_GROUP_TO_ROLE,
    CLEAR_LEGACY_USER_ROLES,
    CREATE_GROUP,
    CREATE_PRACTITIONER,
    DEACTIVATE_PRACTITIONER,
    DELETE_GROUP,
    GET_ENTRA_SHADOW_GROUP,
    GET_PRACTITIONER_ORG_IDS,
    GET_ROLE,
    LIST_GROUP_MEMBERS,
    LIST_GROUPS,
    LIST_GROUPS_SCOPED,
    LIST_ORG_PRACTITIONERS,
    LIST_PRACTITIONERS,
    LIST_PRACTITIONERS_SCOPED,
    LIST_ROLES,
    LIST_USER_ROLES,
    REMOVE_GROUP_MEMBER,
    REMOVE_PRACTITIONER_FROM_ORG,
    REMOVE_USER_ROLE,
    SET_USER_GROUPS,
    UNBIND_ENTRA_GROUP_ROLE,
    UPDATE_GROUP,
    UPDATE_PRACTITIONER,
    UPDATE_PRACTITIONER_LAST_SEEN,
    UPSERT_ENTRA_SHADOW_GROUP,
)

# ------------------------------------------------------------------
# Organisations
# ------------------------------------------------------------------

LIST_ORGS = """
MATCH (o)
WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization
OPTIONAL MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
WHERE (gp.id = o.id)
   OR (gp)-[:COMMISSIONED_BY]->(o)
   OR (gp)-[:PART_OF_PCN]->(:PCN)-[:COMMISSIONED_BY]->(o)
   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(o)
WITH o, count(DISTINCT p) AS patient_count
OPTIONAL MATCH (o)-[:COMMISSIONED_BY]->(parent)
OPTIONAL MATCH (o)-[:PART_OF_ALLIANCE]->(alliance)
OPTIONAL MATCH (o)-[:PART_OF_PCN]->(pcn_parent:PCN)
OPTIONAL MATCH (o)-[:HAS_SUBSCRIPTION]->(sub:Subscription)
RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, o.short_name AS short_name,
       o.azureTenantId AS azureTenantId, o.onboarding_status AS onboarding_status,
       o.ods_sync_status AS ods_sync_status, o.ods_discrepancy AS ods_discrepancy,
       o.ods_sync_last_checked AS ods_sync_last_checked,
       labels(o) AS labels, patient_count,
       parent.id AS parent_id, parent.name AS parent_name,
       alliance.id AS alliance_id, alliance.name AS alliance_name,
       pcn_parent.id AS pcn_id, pcn_parent.name AS pcn_name,
       sub.id AS subscription_id, sub.tier AS subscription_tier,
       sub.credits_purchased AS credits_purchased,
       sub.credits_consumed AS credits_consumed,
       sub.expires_at AS subscription_expires_at,
       CASE
         WHEN 'GPPractice'       IN labels(o) THEN 'gp'
         WHEN 'ICB'              IN labels(o) THEN 'icb'
         WHEN 'CancerAlliance'   IN labels(o) THEN 'alliance'
         WHEN 'PCN'              IN labels(o) THEN 'pcn'
         WHEN 'ServiceProvider'  IN labels(o) THEN 'service_provider'
         WHEN parent IS NOT NULL               THEN 'gp'
         WHEN alliance IS NOT NULL             THEN 'icb'
         ELSE 'organization'
       END AS org_type
ORDER BY o.name
"""

LIST_ORGS_SCOPED = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization)
  AND o.id IN $scope_org_ids
OPTIONAL MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp)
WHERE (gp.id = o.id)
   OR (gp)-[:COMMISSIONED_BY]->(o)
   OR (gp)-[:PART_OF_PCN]->(:PCN)-[:COMMISSIONED_BY]->(o)
   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(o)
WITH o, count(DISTINCT p) AS patient_count
OPTIONAL MATCH (o)-[:COMMISSIONED_BY]->(parent)
OPTIONAL MATCH (o)-[:PART_OF_ALLIANCE]->(alliance)
OPTIONAL MATCH (o)-[:PART_OF_PCN]->(pcn_parent:PCN)
OPTIONAL MATCH (o)-[:HAS_SUBSCRIPTION]->(sub:Subscription)
RETURN o.id AS id, o.name AS name, o.odsCode AS odsCode, o.short_name AS short_name,
       o.azureTenantId AS azureTenantId, o.onboarding_status AS onboarding_status,
       o.ods_sync_status AS ods_sync_status, o.ods_discrepancy AS ods_discrepancy,
       o.ods_sync_last_checked AS ods_sync_last_checked,
       labels(o) AS labels, patient_count,
       parent.id AS parent_id, parent.name AS parent_name,
       alliance.id AS alliance_id, alliance.name AS alliance_name,
       pcn_parent.id AS pcn_id, pcn_parent.name AS pcn_name,
       sub.id AS subscription_id, sub.tier AS subscription_tier,
       sub.credits_purchased AS credits_purchased,
       sub.credits_consumed AS credits_consumed,
       sub.expires_at AS subscription_expires_at,
       CASE
         WHEN 'GPPractice'       IN labels(o) THEN 'gp'
         WHEN 'ICB'              IN labels(o) THEN 'icb'
         WHEN 'CancerAlliance'   IN labels(o) THEN 'alliance'
         WHEN 'PCN'              IN labels(o) THEN 'pcn'
         WHEN 'ServiceProvider'  IN labels(o) THEN 'service_provider'
         WHEN parent IS NOT NULL               THEN 'gp'
         WHEN alliance IS NOT NULL             THEN 'icb'
         ELSE 'organization'
       END AS org_type
ORDER BY o.name
"""

# Name-only catalog for pickers. Do not count patients here.
LIST_ORGS_BRIEF = """
MATCH (o)
WHERE o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization
RETURN o.id AS id, o.name AS name
ORDER BY o.name
"""

LIST_ORGS_BRIEF_SCOPED = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization)
  AND o.id IN $scope_org_ids
RETURN o.id AS id, o.name AS name
ORDER BY o.name
"""

CREATE_ORG_GP = """
CREATE (o:GPPractice:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name,
    o.azureTenantId = $azureTenantId, o.onboarding_status = $onboarding_status,
    o.created_at = datetime()
RETURN o.id AS id
"""

CREATE_ORG_ICB = """
CREATE (o:ICB:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name,
    o.azureTenantId = $azureTenantId, o.onboarding_status = $onboarding_status,
    o.created_at = datetime()
RETURN o.id AS id
"""

CREATE_ORG_ALLIANCE = """
CREATE (o:CancerAlliance:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name,
    o.azureTenantId = $azureTenantId, o.onboarding_status = $onboarding_status,
    o.created_at = datetime()
RETURN o.id AS id
"""

CREATE_ORG_PCN = """
CREATE (o:PCN:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name,
    o.azureTenantId = $azureTenantId, o.onboarding_status = $onboarding_status,
    o.created_at = datetime()
RETURN o.id AS id
"""

CREATE_ORG_SERVICE_PROVIDER = """
CREATE (o:ServiceProvider:Organization)
SET o.id = $id, o.name = $name, o.odsCode = $ods_code, o.short_name = $short_name,
    o.azureTenantId = $azureTenantId, o.onboarding_status = $onboarding_status,
    o.created_at = datetime()
RETURN o.id AS id
"""

# Startup seed for the Mizaic vendor org. organization_id must be set on
# create: the patient graph requires that property on :Organization.
MERGE_MIZAIC_ORGANIZATION = (
    "MERGE (o:Organization {id: $id}) "
    "ON CREATE SET o.organization_id = $id, o.name = $name, "
    "              o.odsCode = '', o.short_name = 'Mizaic', "
    "              o.azureTenantId = $azureTenantId "
    "ON MATCH SET o.organization_id = coalesce(o.organization_id, $id), "
    "             o.azureTenantId = coalesce(nullif(o.azureTenantId, ''), "
    "             nullif($azureTenantId, ''))"
)

MERGE_ORG_BY_AZURE_TENANT = """
MERGE (o:Organization {azureTenantId: $azureTenantId})
ON CREATE SET
  o.id = $id,
  o.organization_id = $id,
  o.name = $name,
  o.short_name = $short_name,
  o.odsCode = '',
  o.created_at = datetime()
ON MATCH SET
  o.organization_id = coalesce(o.organization_id, o.id, $id)
RETURN o.id AS id, o.name AS name
"""

UPDATE_ORG = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization) AND o.id = $id
SET o += $updates
RETURN o.id AS id
"""

DELETE_ORG = """
MATCH (o)
WHERE (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
   OR o:ServiceProvider OR o:Organization) AND o.id = $id
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
WHERE (child:GPPractice OR child:PCN OR child:ServiceProvider OR child:Organization)
  AND child.id = $child_id
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

LINK_GP_TO_PCN = """
MATCH (gp:GPPractice {id: $gp_id}), (pcn:PCN {id: $pcn_id})
MERGE (gp)-[r:PART_OF_PCN]->(pcn)
ON CREATE SET r.effective_from = $effective_from, r.effective_to = null
RETURN gp.id AS id
"""

RELEASE_GP_FROM_PCN = """
MATCH (gp:GPPractice {id: $gp_id})-[r:PART_OF_PCN]->(pcn:PCN {id: $pcn_id})
WHERE r.effective_to IS NULL
SET r.effective_to = $effective_to
RETURN gp.id AS id
"""


# ------------------------------------------------------------------
# Subscriptions
# ------------------------------------------------------------------

CREATE_SUBSCRIPTION = """
MATCH (o:Organization {id: $org_id})
CREATE (s:Subscription)
SET s.id = $id,
    s.org_id = $org_id,
    s.tier = $tier,
    s.seat_count = $seat_count,
    s.credits_purchased = $credits_purchased,
    s.credits_consumed = 0,
    s.purchase_ref = $purchase_ref,
    s.expires_at = $expires_at,
    s.created_at = datetime()
MERGE (o)-[:HAS_SUBSCRIPTION]->(s)
RETURN s.id AS id
"""

DECREMENT_SUBSCRIPTION_CREDITS = """
MATCH (o:Organization {id: $org_id})-[:HAS_SUBSCRIPTION]->(s:Subscription)
WHERE s.credits_consumed < s.credits_purchased
SET s.credits_consumed = s.credits_consumed + $amount
RETURN s.credits_consumed AS credits_consumed, s.credits_purchased AS credits_purchased
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

# ------------------------------------------------------------------
# ODS nightly sync
# ------------------------------------------------------------------

# ODS-driven relabelling — applied automatically when ODS confirms an org's type.
# Adds the specific label while keeping :Organization (base label used across all queries).
RELABEL_ORG_AS_GP = """
MATCH (o:Organization {id: $org_id})
SET o:GPPractice
RETURN o.id AS id
"""

RELABEL_ORG_AS_ICB = """
MATCH (o:Organization {id: $org_id})
SET o:ICB
RETURN o.id AS id
"""

RELABEL_ORG_AS_ALLIANCE = """
MATCH (o:Organization {id: $org_id})
SET o:CancerAlliance
RETURN o.id AS id
"""

RELABEL_ORG_AS_PCN = """
MATCH (o:Organization {id: $org_id})
SET o:PCN
RETURN o.id AS id
"""

RELABEL_ORG_AS_SERVICE_PROVIDER = """
MATCH (o:Organization {id: $org_id})
SET o:ServiceProvider
RETURN o.id AS id
"""

LIST_ORG_SERVICES = """
MATCH (o)
WHERE o.id = $org_id
  AND (o:GPPractice OR o:ICB OR o:CancerAlliance OR o:PCN
       OR o:ServiceProvider OR o:Organization)
MATCH (s:Service)
WHERE (s)-[:PROVIDES_SERVICE_FOR]->(o)
RETURN DISTINCT s.id AS id, s.name AS name, s.code AS code
ORDER BY s.name
"""

LIST_ORGS_WITH_ODS_CODE = """
MATCH (o:Organization)
WHERE o.odsCode IS NOT NULL AND o.odsCode <> ''
OPTIONAL MATCH (o)-[:COMMISSIONED_BY]->(parent_icb:ICB)
OPTIONAL MATCH (o)-[:PART_OF_ALLIANCE]->(parent_ca:CancerAlliance)
OPTIONAL MATCH (o)-[:PART_OF_PCN]->(parent_pcn:PCN)
WITH o, labels(o) AS labels,
     coalesce(parent_icb.odsCode, parent_ca.odsCode, parent_pcn.odsCode) AS current_parent_ods_code
RETURN o.id AS id, o.odsCode AS ods_code, o.name AS name,
       o.ods_sync_status AS ods_sync_status, labels,
       current_parent_ods_code
ORDER BY o.id
"""

UPDATE_ORG_ODS_SYNC = """
MATCH (o:Organization {id: $org_id})
SET o.ods_sync_last_checked = $checked_at,
    o.ods_sync_status = $status,
    o.ods_discrepancy = $discrepancy,
    o.ods_run_id = $run_id,
    o.ods_parent_ods_code = $ods_parent_ods_code,
    o.ods_address = $ods_address
RETURN o.id AS id
"""

BATCH_UPDATE_ODS_CHECKED = """
UNWIND $orgs AS row
MATCH (o:Organization {id: row.id})
SET o.ods_sync_last_checked = row.checked_at,
    o.ods_run_id = row.run_id,
    o.ods_parent_ods_code = row.ods_parent_ods_code,
    o.ods_address = row.ods_address
RETURN count(o) AS updated
"""

GET_ORG_GRAPH = """
MATCH (n)
WHERE n:GPPractice OR n:ICB OR n:CancerAlliance OR n:PCN OR n:ServiceProvider
OPTIONAL MATCH (n)-[:COMMISSIONED_BY]->(icb:ICB)
OPTIONAL MATCH (n)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance)
OPTIONAL MATCH (n)-[:PART_OF_PCN]->(pcn:PCN)
OPTIONAL MATCH (n)<-[:HAS_GENERAL_PRACTITIONER]-(p:Patient)
RETURN
  n.id AS id,
  n.name AS name,
  n.odsCode AS odsCode,
  n.short_name AS short_name,
  labels(n) AS labels,
  n.ods_sync_status AS ods_sync_status,
  n.ods_parent_ods_code AS ods_parent_ods_code,
  n.ods_address AS ods_address,
  n.onboarding_status AS onboarding_status,
  icb.id AS parent_icb_id,
  ca.id AS parent_ca_id,
  pcn.id AS parent_pcn_id,
  count(DISTINCT p) AS patient_count
ORDER BY n.name
"""
