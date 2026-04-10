from __future__ import annotations

import sys
import types


def _import_split_sentences():
    if "langgraph.graph" not in sys.modules:
        graph_mod = types.SimpleNamespace(
            END="END",
            START="START",
            StateGraph=type("StateGraph", (), {}),
        )
        state_mod = types.SimpleNamespace(CompiledStateGraph=object)
        sys.modules["langgraph.graph"] = graph_mod
        sys.modules["langgraph.graph.state"] = state_mod

    from libs.pipeline_graph.subgraphs.extraction import split_sentences

    return split_sentences


def test_split_sentences_uses_existing_encounter_text() -> None:
    split_sentences = _import_split_sentences()
    result = split_sentences(
        {
            "encounter_id": "enc-1",
            "encounter_text": "Patient has chest pain.",
        }
    )
    assert result["encounter_text"] == "Patient has chest pain."
    assert len(result["sentences"]) == 1


def test_split_sentences_hydrates_missing_text_from_graph(monkeypatch) -> None:
    split_sentences = _import_split_sentences()

    class _FakeClient:
        def run(self, _query: str, **_kwargs):
            return [{"text": "Hydrated note text."}]

        def close(self):
            return None

    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient",
        _FakeClient,
    )

    result = split_sentences(
        {
            "encounter_id": "enc-2",
            "encounter_text": "",
        }
    )
    assert result["encounter_text"] == "Hydrated note text."
    assert len(result["sentences"]) == 1
