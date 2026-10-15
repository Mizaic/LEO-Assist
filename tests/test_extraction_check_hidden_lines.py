"""The extraction check must not add back a fact the form told LEO to hide.

The extraction check is a second model pass that may add facts the first
pass missed. It reads the raw letter, so it can see lines the taught form
marked non-extractable. On the Sherwood Forest lower GI 2WW dry run
(2026-10-13) it added "eGFR" as planned from the printed guidance "if
older please arrange FBC, U&Es & eGFR", after the normaliser had sealed
that line for the main extraction.

The rule under test: an added fact whose words appear only on lines the
normaliser marked non-extractable is dropped and the drop is recorded. If
the words also appear on a line the model may use, the fact is kept.
With no normalised sentences in state, nothing is known to be hidden and
additions behave as before.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER  # noqa: E402
from libs.pipeline_graph.subgraphs.llm_check import (  # noqa: E402
    build_extraction_check_subgraph,
)

GUIDANCE = (
    "| * Blood results within 12 weeks are required before sending referral "
    "- if older please arrange FBC, U&Es & eGFR. |"
)
ADD_EGFR = '{"add":[{"text":"eGFR","label":"procedure","assertion":"planned"}]}'


class _Resp:
    def __init__(self, text: str):
        self.text = text


class _LLM:
    def __init__(self, text: str):
        self._text = text

    def converse(self, **kwargs):
        return _Resp(self._text)


def _sentences(*lines: tuple[str, bool]) -> list[dict]:
    raw = "\n".join(text for text, _ in lines)
    shown = "\n".join(
        f"{NON_EXTRACTABLE_MARKER} {text}" if hidden else text for text, hidden in lines
    )
    return [{"sentence_id": "s0", "text": shown, "text_raw": raw}]


def _run(monkeypatch, payload: str, state: dict) -> dict:
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm",
        lambda tier="small": _LLM(payload),
    )
    return build_extraction_check_subgraph().invoke(state)


def _texts(out: dict) -> list[str]:
    return [str(e.get("text")) for e in out["entities"]]


def test_added_fact_only_on_a_hidden_line_is_dropped(monkeypatch) -> None:
    lines = ((GUIDANCE, True), ("| Needs blood tests. |", False))
    out = _run(
        monkeypatch,
        ADD_EGFR,
        {
            "encounter_text": "\n".join(text for text, _ in lines),
            "entities": [],
            "sentences": _sentences(*lines),
        },
    )
    assert "eGFR" not in _texts(out)
    assert any(
        c.get("type") == "drop_add"
        and c.get("text") == "eGFR"
        and c.get("reason") == "only_on_non_extractable_line"
        for c in out["llm_check_changes"]
    )


def test_added_fact_also_on_a_usable_line_is_kept(monkeypatch) -> None:
    lines = ((GUIDANCE, True), ("| Recheck eGFR next week. |", False))
    out = _run(
        monkeypatch,
        ADD_EGFR,
        {
            "encounter_text": "\n".join(text for text, _ in lines),
            "entities": [],
            "sentences": _sentences(*lines),
        },
    )
    assert "eGFR" in _texts(out)


def test_without_sentences_additions_behave_as_before(monkeypatch) -> None:
    out = _run(
        monkeypatch,
        ADD_EGFR,
        {"encounter_text": GUIDANCE, "entities": []},
    )
    assert "eGFR" in _texts(out)
