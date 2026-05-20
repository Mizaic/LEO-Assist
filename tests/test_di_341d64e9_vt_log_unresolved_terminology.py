"""VT for DI-341D64E9 AC3: log when no safe recognised clinical term is available."""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.terminology import _resolve_terms
from libs.terminology.client import ResolvedTerm, TerminologyClient


def test_no_safe_term_marks_unresolved_and_logs_terminology_low_confidence() -> None:
    entities = [{"text": "fatigue", "label": "finding"}]

    def _fake_batch(self, terms, expected_tags, runtime):
        return {
            "fatigue": [
                ResolvedTerm(
                    text="fatigue",
                    concept_id="84229001",
                    term="Fatigue",
                    semantic_tag="finding",
                    score=0.40,
                )
            ]
        }

    with patch.object(TerminologyClient, "_resolve_batch", _fake_batch):
        result = _resolve_terms(
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.55}
        )

    unresolved = result["resolved_entities"][0]
    assert unresolved["terminology_unresolved"] is True
    errors = result.get("errors") or []
    assert any(err.startswith("terminology_low_confidence:") for err in errors)
    assert '"fatigue"' in errors[0]
