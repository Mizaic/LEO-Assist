"""Tests for `services/terminology_api/app/queries/conceptmap.py` and
`valueset.py`.

Atlas trace:
  DO: DO-1373B71F
  DI: DI-17B5738E

Cypher contract checks: every CRUD query MUST reference its parameter,
ORDER BY / SKIP / LIMIT are present on paged searches, the upsert
returns rawJson, and the delete uses DETACH DELETE.
"""

from __future__ import annotations

import re

from services.terminology_api.app.queries import conceptmap as cm
from services.terminology_api.app.queries import valueset as vs


def _params(text: str) -> set[str]:
    return set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", text))


class TestConceptMapUpsert:
    def test_uses_merge_keyed_on_id(self):
        assert "MERGE (c:ConceptMap {id: $conceptMapId})" in cm.CONCEPTMAP_UPSERT

    def test_returns_raw_json_for_round_trip(self):
        assert "RETURN c.rawJson AS rawJson" in cm.CONCEPTMAP_UPSERT

    def test_marks_concept_map_as_global(self):
        assert "c.isGlobal  = true" in cm.CONCEPTMAP_UPSERT
        assert "c.tenantId  = null" in cm.CONCEPTMAP_UPSERT

    def test_all_documented_params_referenced(self):
        params = _params(cm.CONCEPTMAP_UPSERT)
        for p in (
            "conceptMapId",
            "rawJson",
            "url",
            "name",
            "title",
            "status",
            "version",
            "sourceUri",
            "targetUri",
        ):
            assert p in params


class TestConceptMapReadAndDelete:
    def test_get_limited_to_one(self):
        assert "LIMIT 1" in cm.CONCEPTMAP_GET

    def test_delete_uses_detach_delete(self):
        assert "DETACH DELETE c" in cm.CONCEPTMAP_DELETE

    def test_search_supports_filters_and_pagination(self):
        params = _params(cm.CONCEPTMAP_SEARCH)
        for p in ("name", "status", "url", "offset", "limit"):
            assert p in params
        assert "ORDER BY c.name" in cm.CONCEPTMAP_SEARCH

    def test_count_returns_total(self):
        assert "count(c) AS total" in cm.CONCEPTMAP_COUNT


class TestValueSetUpsert:
    def test_uses_merge_keyed_on_id(self):
        assert "MERGE (v:ValueSet {id: $valueSetId})" in vs.VALUESET_UPSERT

    def test_returns_raw_json_for_round_trip(self):
        assert "RETURN v.rawJson AS rawJson" in vs.VALUESET_UPSERT

    def test_marks_value_set_as_global(self):
        assert "v.isGlobal  = true" in vs.VALUESET_UPSERT
        assert "v.tenantId  = null" in vs.VALUESET_UPSERT


class TestValueSetReadAndDelete:
    def test_get_by_url_orders_by_version_desc(self):
        assert "ORDER BY v.version DESC" in vs.VALUESET_GET_BY_URL
        assert "LIMIT 1" in vs.VALUESET_GET_BY_URL

    def test_delete_uses_detach_delete(self):
        assert "DETACH DELETE v" in vs.VALUESET_DELETE

    def test_search_supports_filters_and_pagination(self):
        params = _params(vs.VALUESET_SEARCH)
        for p in ("name", "status", "url", "offset", "limit"):
            assert p in params
        assert "ORDER BY v.name" in vs.VALUESET_SEARCH

    def test_count_returns_total(self):
        assert "count(v) AS total" in vs.VALUESET_COUNT
