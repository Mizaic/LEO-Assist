"""Static verification of libs/cypher/lock_queries.py.

These tests do not need a live Neo4j; they assert that the Cypher
strings carry the parameters and structure required by lock_service so
a refactor cannot silently drop a field.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from __future__ import annotations

from libs.cypher import lock_queries as q


def test_indexes_define_unique_lock_id_and_composite_lookup() -> None:
    indexes = q.CREATE_LOCK_INDEXES
    assert any(
        "verification_lock_id" in s and "REQUIRE l.lock_id IS UNIQUE" in s
        for s in indexes
    )
    assert any(
        "verification_lock_entity" in s
        and "(l.entity_type, l.entity_id)" in s
        for s in indexes
    )
    assert any("verification_lock_locked_by" in s for s in indexes)


def test_upsert_lock_carries_full_lock_record() -> None:
    cypher = q.UPSERT_LOCK
    for param in (
        "$entity_type",
        "$entity_id",
        "$lock_id",
        "$locked_by",
        "$locked_by_role",
        "$lock_reason",
        "$source",
    ):
        assert param in cypher, f"missing parameter {param} in UPSERT_LOCK"
    assert "datetime()" in cypher
    assert "RETURN" in cypher
    assert "l.lock_id AS lock_id" in cypher
    assert "l.entity_type AS entity_type" in cypher


def test_match_lock_uses_composite_key_and_returns_full_record() -> None:
    cypher = q.MATCH_LOCK
    assert "{entity_type: $entity_type, entity_id: $entity_id}" in cypher
    assert "l.locked_by AS locked_by" in cypher
    assert "l.locked_by_role AS locked_by_role" in cypher


def test_release_lock_deletes_node_and_returns_identity() -> None:
    cypher = q.RELEASE_LOCK
    assert "{lock_id: $lock_id}" in cypher
    assert "DELETE l" in cypher
    assert "RETURN released_lock_id AS lock_id" in cypher
    assert "entity_type" in cypher
    assert "entity_id" in cypher


def test_list_for_entity_type_supports_optional_id_filter() -> None:
    cypher = q.LIST_LOCKS_FOR_ENTITY_TYPE
    assert "{entity_type: $entity_type}" in cypher
    assert "$entity_ids IS NULL OR l.entity_id IN $entity_ids" in cypher


def test_list_for_episode_covers_all_lockable_entity_types() -> None:
    cypher = q.LIST_LOCKS_FOR_EPISODE
    assert "EpisodeOfCare {id: $episode_id}" in cypher
    for entity_type in ("episode", "encounter", "is_part_of_edge"):
        assert f"'{entity_type}'" in cypher
    assert "['coded_link', 'assertion']" in cypher
    assert "STARTS WITH" in cypher


def test_list_for_patient_walks_patient_episode_encounter_graph() -> None:
    cypher = q.LIST_LOCKS_FOR_PATIENT
    assert "Patient {id: $patient_id}" in cypher
    assert "HAS_ENCOUNTER" in cypher
    assert "IS_PART_OF" in cypher
    for entity_type in (
        "episode",
        "encounter",
        "is_part_of_edge",
    ):
        assert f"'{entity_type}'" in cypher


def test_count_locks_uses_composite_key() -> None:
    cypher = q.COUNT_LOCKS_FOR_ENTITY
    assert "{entity_type: $entity_type, entity_id: $entity_id}" in cypher
    assert "RETURN count(l) AS total" in cypher
