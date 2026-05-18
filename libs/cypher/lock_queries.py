"""Cypher queries for VerificationLock cross-entity primitive.

A VerificationLock node marks a reviewer-confirmed entity (episode,
encounter, IS_PART_OF edge, coded link, assertion) as immutable to all
automated mutation paths. Lookups are by composite key (entity_type,
entity_id). Writes go through libs/locks/lock_service.apply_with_lock so
the mutation, the lock and the HumanReconciliation AuditEvent land in a
single transaction.

Entity-type vocabulary (libs.locks.models.LockEntityType):
- 'episode'           -- (:EpisodeOfCare {id})
- 'encounter'         -- (:Encounter {id})
- 'is_part_of_edge'   -- composite key: '<encounter_id>:<episode_id>'
- 'coded_link'        -- composite key: '<encounter_id>:<concept_id>'
- 'assertion'         -- composite key: '<encounter_id>:<entity_id>'

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

CREATE_LOCK_INDEXES = [
    (
        "CREATE CONSTRAINT verification_lock_id IF NOT EXISTS "
        "FOR (l:VerificationLock) REQUIRE l.lock_id IS UNIQUE"
    ),
    (
        "CREATE INDEX verification_lock_entity IF NOT EXISTS "
        "FOR (l:VerificationLock) ON (l.entity_type, l.entity_id)"
    ),
    (
        "CREATE INDEX verification_lock_locked_by IF NOT EXISTS "
        "FOR (l:VerificationLock) ON (l.locked_by)"
    ),
]

UPSERT_LOCK = """
MERGE (l:VerificationLock {entity_type: $entity_type, entity_id: $entity_id})
ON CREATE SET
    l.lock_id = $lock_id,
    l.locked_by = $locked_by,
    l.locked_by_role = $locked_by_role,
    l.lock_reason = $lock_reason,
    l.source = $source,
    l.locked_at = datetime(),
    l.updated_at = datetime()
ON MATCH SET
    l.locked_by = $locked_by,
    l.locked_by_role = $locked_by_role,
    l.lock_reason = $lock_reason,
    l.source = $source,
    l.updated_at = datetime()
RETURN
    l.lock_id AS lock_id,
    l.entity_type AS entity_type,
    l.entity_id AS entity_id,
    l.locked_by AS locked_by,
    l.locked_by_role AS locked_by_role,
    l.lock_reason AS lock_reason,
    l.source AS source,
    toString(l.locked_at) AS locked_at,
    toString(l.updated_at) AS updated_at
"""

MATCH_LOCK = """
MATCH (l:VerificationLock {entity_type: $entity_type, entity_id: $entity_id})
RETURN
    l.lock_id AS lock_id,
    l.entity_type AS entity_type,
    l.entity_id AS entity_id,
    l.locked_by AS locked_by,
    l.locked_by_role AS locked_by_role,
    l.lock_reason AS lock_reason,
    l.source AS source,
    toString(l.locked_at) AS locked_at,
    toString(l.updated_at) AS updated_at
"""

RELEASE_LOCK = """
MATCH (l:VerificationLock {lock_id: $lock_id})
WITH l, l.entity_type AS entity_type, l.entity_id AS entity_id,
     l.lock_id AS released_lock_id
DELETE l
RETURN released_lock_id AS lock_id, entity_type, entity_id
"""

LIST_LOCKS_FOR_ENTITY_TYPE = """
MATCH (l:VerificationLock {entity_type: $entity_type})
WHERE $entity_ids IS NULL OR l.entity_id IN $entity_ids
RETURN
    l.lock_id AS lock_id,
    l.entity_type AS entity_type,
    l.entity_id AS entity_id,
    l.locked_by AS locked_by,
    l.locked_by_role AS locked_by_role,
    l.lock_reason AS lock_reason,
    l.source AS source,
    toString(l.locked_at) AS locked_at
ORDER BY l.locked_at DESC
"""

# All locks attached to an episode itself, every encounter that
# IS_PART_OF that episode, every IS_PART_OF edge into the episode and
# every coded link / assertion on those encounters. Used by the rebuild
# guard and the UI lock-chip surface.
LIST_LOCKS_FOR_EPISODE = """
MATCH (ep:EpisodeOfCare {id: $episode_id})
OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
WITH ep, collect(DISTINCT enc.id) AS encounter_ids
WITH ep,
     encounter_ids,
     [eid IN encounter_ids | eid + ':' + ep.id] AS edge_keys
MATCH (l:VerificationLock)
WHERE
    (l.entity_type = 'episode' AND l.entity_id = ep.id)
    OR (l.entity_type = 'encounter' AND l.entity_id IN encounter_ids)
    OR (l.entity_type = 'is_part_of_edge' AND l.entity_id IN edge_keys)
    OR (
        l.entity_type IN ['coded_link', 'assertion']
        AND any(eid IN encounter_ids WHERE l.entity_id STARTS WITH (eid + ':'))
    )
RETURN
    l.lock_id AS lock_id,
    l.entity_type AS entity_type,
    l.entity_id AS entity_id,
    l.locked_by AS locked_by,
    l.locked_by_role AS locked_by_role,
    l.lock_reason AS lock_reason,
    l.source AS source,
    toString(l.locked_at) AS locked_at
ORDER BY l.locked_at DESC
"""

# All locks visible to anyone reviewing this patient. Used by the
# Mission Control patient panel and the rebuild guard for the patient
# graph as a whole.
LIST_LOCKS_FOR_PATIENT = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)
OPTIONAL MATCH (enc)-[:IS_PART_OF]->(ep:EpisodeOfCare)
WITH collect(DISTINCT enc.id) AS encounter_ids,
     collect(DISTINCT ep.id) AS episode_ids
WITH encounter_ids, episode_ids,
     [eid IN encounter_ids |
        [pid IN episode_ids | eid + ':' + pid]] AS edge_keys_nested
WITH encounter_ids, episode_ids,
     reduce(acc = [], xs IN edge_keys_nested | acc + xs) AS edge_keys
MATCH (l:VerificationLock)
WHERE
    (l.entity_type = 'episode' AND l.entity_id IN episode_ids)
    OR (l.entity_type = 'encounter' AND l.entity_id IN encounter_ids)
    OR (l.entity_type = 'is_part_of_edge' AND l.entity_id IN edge_keys)
    OR (
        l.entity_type IN ['coded_link', 'assertion']
        AND any(eid IN encounter_ids WHERE l.entity_id STARTS WITH (eid + ':'))
    )
RETURN
    l.lock_id AS lock_id,
    l.entity_type AS entity_type,
    l.entity_id AS entity_id,
    l.locked_by AS locked_by,
    l.locked_by_role AS locked_by_role,
    l.lock_reason AS lock_reason,
    l.source AS source,
    toString(l.locked_at) AS locked_at
ORDER BY l.locked_at DESC
"""

COUNT_LOCKS_FOR_ENTITY = """
MATCH (l:VerificationLock {entity_type: $entity_type, entity_id: $entity_id})
RETURN count(l) AS total
"""
