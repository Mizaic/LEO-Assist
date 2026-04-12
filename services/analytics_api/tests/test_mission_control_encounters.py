from __future__ import annotations

import sys
import types

import pytest

# Test envs may not have Azure SDK installed; stub required imports used by config.
azure_mod = types.ModuleType("azure")
azure_identity_mod = types.ModuleType("azure.identity")
azure_keyvault_mod = types.ModuleType("azure.keyvault")
azure_keyvault_secrets_mod = types.ModuleType("azure.keyvault.secrets")


class _DummyAzureClient:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)


azure_identity_mod.DefaultAzureCredential = _DummyAzureClient
azure_keyvault_secrets_mod.SecretClient = _DummyAzureClient
sys.modules.setdefault("azure", azure_mod)
sys.modules.setdefault("azure.identity", azure_identity_mod)
sys.modules.setdefault("azure.keyvault", azure_keyvault_mod)
sys.modules.setdefault("azure.keyvault.secrets", azure_keyvault_secrets_mod)

from services.analytics_api.app.routers import mission_control_encounters as mce


def test_sort_clause_defaults_to_date_desc():
    clause = mce._sort_clause("unknown", "BAD")
    assert "toString(e.date)" in clause
    assert "DESC" in clause


def test_append_filters_adds_patient_and_date():
    base, params = mce._append_filters(
        "MATCH (p)-[:HAS_ENCOUNTER]->(e) WHERE true ",
        {},
        date_from="2025-01-01",
        date_to="2025-12-31",
        patient_id="123",
    )
    assert "toString(e.date) >= $date_from" in base
    assert "toString(e.date) <= $date_to" in base
    assert "toString(p.id) = $patient_id" in base
    assert params["patient_id"] == "123"


@pytest.mark.asyncio
async def test_encounter_list_without_search_returns_rows(monkeypatch):
    class _FakeClient:
        def run(self, query, **kwargs):
            if "count(DISTINCT e) AS total" in query:
                return [{"total": 1}]
            if "RETURN toString(e.id) AS encounter_id" in query:
                return [
                    {
                        "encounter_id": "enc-1",
                        "patient_id": "p-1",
                        "encounter_date": "2025-01-01",
                        "text": "Patient has cough",
                        "flags": [],
                        "coded_count": 2,
                    }
                ]
            return []

        def close(self):
            return None

    monkeypatch.setattr(mce, "PatientGraphClient", _FakeClient)

    result = await mce.get_mission_control_encounters(
        org_id="org-1",
        date_from=None,
        date_to=None,
        patient_id=None,
        q=None,
        page=1,
        page_size=25,
        max_results=2000,
        near_duplicate_threshold=None,
        sort_by="encounter_date",
        sort_dir="DESC",
        scope=type(
            "S",
            (),
            {
                "is_admin": True,
                "primary_org_id": None,
                "to_query_params": lambda self: {},
            },
        )(),
    )
    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["match_type"] == "none"


@pytest.mark.asyncio
async def test_hybrid_search_fallback_when_indexes_unavailable(monkeypatch):
    class _FakeClient:
        def run(self, query, **kwargs):
            raise RuntimeError("index unavailable")

        def close(self):
            return None

    monkeypatch.setattr(mce, "PatientGraphClient", _FakeClient)
    monkeypatch.setattr(mce, "_try_embed_query", lambda _q: [0.1, 0.2])

    result = await mce.get_mission_control_encounters(
        org_id="org-1",
        date_from=None,
        date_to=None,
        patient_id=None,
        q="cough",
        page=1,
        page_size=25,
        max_results=2000,
        near_duplicate_threshold=None,
        sort_by="encounter_date",
        sort_dir="DESC",
        scope=type(
            "S",
            (),
            {
                "is_admin": True,
                "primary_org_id": None,
                "to_query_params": lambda self: {},
            },
        )(),
    )
    assert result["total"] == 0
    assert result["items"] == []


@pytest.mark.asyncio
async def test_hybrid_search_returns_query_diagnostics(monkeypatch):
    class _FakeClient:
        def run(self, query, **kwargs):
            if "fulltext.queryNodes" in query:
                return [
                    {
                        "encounter_id": "enc-1",
                        "patient_id": "p-1",
                        "encounter_date": "2025-01-01",
                        "text": "breast lump and weight loss",
                        "flags": [],
                        "coded_count": 2,
                        "fulltext_score": 3.2,
                    }
                ]
            if "vector.queryNodes" in query:
                return [
                    {
                        "encounter_id": "enc-1",
                        "patient_id": "p-1",
                        "encounter_date": "2025-01-01",
                        "text": "breast lump and weight loss",
                        "flags": [],
                        "coded_count": 2,
                        "vector_score": 0.91,
                    }
                ]
            return []

        def close(self):
            return None

    monkeypatch.setattr(mce, "PatientGraphClient", _FakeClient)
    monkeypatch.setattr(mce, "_try_embed_query", lambda _q: [0.1, 0.2])
    monkeypatch.setattr(mce, "_write_query_audit", lambda **kwargs: None)

    result = await mce.get_mission_control_encounters(
        org_id="org-1",
        date_from=None,
        date_to=None,
        patient_id=None,
        q="breat lump weight loss",
        page=1,
        page_size=25,
        max_results=2000,
        near_duplicate_threshold=0.95,
        sort_by="encounter_date",
        sort_dir="DESC",
        scope=type(
            "S",
            (),
            {
                "is_admin": True,
                "primary_org_id": None,
                "to_query_params": lambda self: {},
            },
        )(),
    )
    assert "query_diagnostics" in result
    assert result["query_diagnostics"]["original_query"] == "breat lump weight loss"
    assert result["items"][0]["match_type"] == "hybrid"
    assert "rank_features" in result["items"][0]


def test_suppress_near_duplicates_filters_similar_text():
    ranked = [
        {"encounter_id": "e1", "text": "breast lump and weight loss"},
        {"encounter_id": "e2", "text": "breast lump with weight loss"},
        {"encounter_id": "e3", "text": "skin lesion on forearm"},
    ]
    kept, filtered = mce._suppress_near_duplicates(ranked, 0.8)
    assert len(kept) == 2
    assert filtered == 1
