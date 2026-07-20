"""VT-F266ECFB -- post_processing auto-loads active package patterns."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.ner.local_concept_recovery import LocalConceptPattern
from libs.pipeline_graph.subgraphs.post_processing import (
    _resolve_local_patterns,
    run_post_process,
)


class TestResolveLocalPatterns:
    def test_injected_patterns_used(self):
        patterns = [
            LocalConceptPattern(
                normalized="acne fulminans",
                form="acne fulminans",
                concept_id="LEO-LOCAL-AF",
                fsn="Acne fulminans (LEO local)",
            )
        ]
        out = _resolve_local_patterns({"local_concept_patterns": patterns})
        assert out == patterns

    def test_empty_injected_skips_load(self):
        out = _resolve_local_patterns({"local_concept_patterns": []})
        assert out == []

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    @patch("libs.ner.local_concept_recovery.load_active_package_patterns")
    def test_loads_when_not_injected(self, mock_load, MockKG):
        mock_load.return_value = [
            LocalConceptPattern(
                normalized="flare",
                form="flare",
                concept_id="LEO-LOCAL-FLARE",
                fsn="Flare (LEO local)",
            )
        ]
        MockKG.return_value = MagicMock()
        out = _resolve_local_patterns({"org_id": "org-A"})
        assert out[0].concept_id == "LEO-LOCAL-FLARE"
        mock_load.assert_called_once()


class TestRunPostProcessRecovery:
    @patch(
        "libs.pipeline_graph.subgraphs.post_processing._resolve_local_patterns"
    )
    @patch("libs.ner.post_processor_rules.parse_rules", return_value=None)
    @patch("libs.pipeline.post_processing.run_post_processing_with_trace")
    def test_passes_patterns_into_post_processing(
        self, mock_run, _parse, mock_resolve
    ):
        patterns = [
            LocalConceptPattern(
                normalized="acne fulminans",
                form="acne fulminans",
                concept_id="LEO-LOCAL-AF",
                fsn="Acne fulminans (LEO local)",
            )
        ]
        mock_resolve.return_value = patterns
        mock_run.return_value = (
            [
                {
                    "text": "acne fulminans",
                    "snomed_concept_id": "LEO-LOCAL-AF",
                }
            ],
            [],
        )
        out = run_post_process(
            {
                "encounter_text": "acne fulminans today",
                "entities": [],
                "org_id": "org-A",
            }
        )
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("local_concept_patterns") == patterns
        assert out["entities"][0]["snomed_concept_id"] == "LEO-LOCAL-AF"

    @patch(
        "libs.pipeline_graph.subgraphs.post_processing._resolve_local_patterns",
        return_value=[],
    )
    @patch("libs.ner.post_processor_rules.parse_rules", return_value=None)
    @patch("libs.pipeline.post_processing.run_post_processing_with_trace")
    def test_empty_patterns_no_throw(self, mock_run, _parse, _resolve):
        mock_run.return_value = ([], [])
        out = run_post_process(
            {"encounter_text": "hello", "entities": [], "org_id": ""}
        )
        assert out["errors"] == []
        assert out["entities"] == []
