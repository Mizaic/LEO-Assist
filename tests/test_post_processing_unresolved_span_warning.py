"""A fact whose assertion was never checked must be visible in the run.

``resolve_context_spans`` flags any fact it cannot locate in the letter with
``context_span_unresolved``. ConText is then skipped for that fact, so its
assertion is whatever the extractor guessed -- and the extractor guesses
``present``. That is the exact shape of the defect that put "abdo full soft,
non tender" into the record as a present finding.

Setting the flag is not enough on its own. ``fail-closed-boundary.mdc``
asks one question of every such site: could a clinician tell from the output
that this happened? A log line cannot be read from the patient record, so
the count has to reach pipeline state as a warning.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.pipeline_graph.subgraphs.post_processing import (
    UNRESOLVED_SPAN_WARNING,
    run_post_process,
)

_LETTER = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n"
    "Section C: Further Clinical details\n"
    "Abdomen full soft, non tender. No palpable mass.\n"
)


def _entity(text: str, start: int, end: int) -> dict[str, Any]:
    return {
        "text": text,
        "label": "finding",
        "start": start,
        "end": end,
        "assertion": "present",
        "sentence_id": "chunk-0",
    }


def _run(entities: list[dict[str, Any]]) -> dict[str, Any]:
    return run_post_process(
        {
            "encounter_text": _LETTER,
            "entities": entities,
            "rules": [],
            "enable_disorder_gate": False,
            "coding_mode": "hitl",
        }
    )


def test_unlocatable_fact_raises_a_warning() -> None:
    """A quote that is nowhere in the letter must be announced, not dropped."""
    result = _run([_entity("hepatosplenomegaly with ascites", 0, 30)])

    warnings = result.get("warnings") or []
    assert any(UNRESOLVED_SPAN_WARNING in w for w in warnings), warnings


def test_warning_names_how_many_facts_were_not_checked() -> None:
    """A person triaging the run needs the size of the problem, not a flag."""
    result = _run(
        [
            _entity("hepatosplenomegaly with ascites", 0, 30),
            _entity("clubbing of the fingers", 0, 23),
            _entity("non tender", _LETTER.index("non tender"), 0),
        ]
    )

    warnings = [
        w for w in (result.get("warnings") or []) if UNRESOLVED_SPAN_WARNING in w
    ]
    assert warnings, result.get("warnings")
    assert "2" in warnings[0], warnings[0]


def test_no_warning_when_every_fact_is_located() -> None:
    """A clean run must stay clean -- no crying wolf."""
    start = _LETTER.index("non tender")
    result = _run([_entity("non tender", start, start + len("non tender"))])

    warnings = [
        w for w in (result.get("warnings") or []) if UNRESOLVED_SPAN_WARNING in w
    ]
    assert not warnings, result.get("warnings")


def test_warning_does_not_erase_earlier_warnings() -> None:
    """Post-processing adds to the run's warnings, it does not replace them."""
    state: dict[str, Any] = {
        "encounter_text": _LETTER,
        "entities": [_entity("hepatosplenomegaly with ascites", 0, 30)],
        "rules": [],
        "enable_disorder_gate": False,
        "coding_mode": "hitl",
        "warnings": ["healthcare_service_missing"],
    }
    result = run_post_process(state)

    warnings = result.get("warnings") or []
    assert "healthcare_service_missing" in warnings
    assert any(UNRESOLVED_SPAN_WARNING in w for w in warnings)
