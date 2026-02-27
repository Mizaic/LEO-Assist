"""Tests for services/analysis-worker/app/analyzers/episode_builder.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult


class TestExtractConditionKey:

    def test_strips_prefixes(self):
        from services.analysis_worker.app.analyzers.episode_builder import _extract_condition_key

        assert _extract_condition_key({"concept_name": "Fast track referral for suspected breast cancer"}) == "breast"
        assert _extract_condition_key({"concept_name": "suspected lung cancer"}) == "lung"
        assert _extract_condition_key({"concept_name": "diagnosis of colorectal carcinoma"}) == "colorectal"

    def test_unknown_fallback(self):
        from services.analysis_worker.app.analyzers.episode_builder import _extract_condition_key

        assert _extract_condition_key({"concept_name": ""}) == "unknown"
        assert _extract_condition_key({}) == "unknown"


class TestSimplifyConditionType:

    def test_strips_prefix_and_cancer(self):
        from services.analysis_worker.app.analyzers.episode_builder import _simplify_condition_type

        assert _simplify_condition_type("Fast track referral for suspected breast cancer") == "breast"
        assert _simplify_condition_type("Unknown") == "Unknown"


class TestBuildEpisodes:

    @pytest.mark.asyncio
    async def test_no_anchors_returns_empty(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(patient_id="P1")
        mock_client = MagicMock()
        result = await build_episodes("P1", anchors, mock_client)
        assert result.episodes_created == 0
        assert result.episode_ids == []

    @pytest.mark.asyncio
    async def test_creates_episode_from_referral(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[{
                "encounter_id": "E1",
                "encounter_date": "2024-03-15",
                "concept_name": "Fast track referral for suspected breast cancer",
                "source": "text_search",
            }],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes("P1", anchors, mock_client)
        assert result.episodes_created == 1
        assert len(result.episode_ids) == 1
        assert mock_client.run.call_count >= 2  # MERGE + MATCH for link

    @pytest.mark.asyncio
    async def test_deduplicates_cancer_types(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {"encounter_id": "E1", "encounter_date": "2024-01-10", "concept_name": "Fast track referral for suspected breast cancer"},
                {"encounter_id": "E2", "encounter_date": "2024-02-10", "concept_name": "Fast track referral for suspected breast cancer"},
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes("P1", anchors, mock_client)
        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_multiple_cancer_types_create_separate_episodes(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {"encounter_id": "E1", "encounter_date": "2024-01-10", "concept_name": "Fast track referral for suspected breast cancer"},
                {"encounter_id": "E2", "encounter_date": "2024-02-10", "concept_name": "Fast track referral for suspected lung cancer"},
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes("P1", anchors, mock_client)
        assert result.episodes_created == 2

    @pytest.mark.asyncio
    async def test_links_diagnosis_encounters(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {"encounter_id": "E1", "encounter_date": "2024-01-10", "concept_name": "suspected breast cancer"},
            ],
            diagnosis_anchors=[
                {"encounter_id": "E2", "encounter_date": "2024-02-10", "concept_name": "confirmed adenocarcinoma"},
            ],
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = await build_episodes("P1", anchors, mock_client)
        assert result.encounters_linked >= 2

    @pytest.mark.asyncio
    async def test_handles_build_error(self):
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = AnchorResult(
            patient_id="P1",
            referral_anchors=[
                {"encounter_id": "E1", "encounter_date": "invalid-date", "concept_name": "suspected breast cancer"},
            ],
        )

        mock_client = MagicMock()
        mock_client.run.side_effect = RuntimeError("db error")

        result = await build_episodes("P1", anchors, mock_client)
        assert len(result.errors) >= 1


class TestTryConsolidate:

    def test_less_than_2_episodes(self):
        from services.analysis_worker.app.analyzers.episode_builder import _try_consolidate

        mock_client = MagicMock()
        assert _try_consolidate(["ep1"], mock_client) == 0
        mock_client.run.assert_not_called()

    def test_merges_overlapping_episodes(self):
        from services.analysis_worker.app.analyzers.episode_builder import _try_consolidate

        mock_client = MagicMock()
        mock_client.run.side_effect = [
            [{"shared": 2}],  # overlap check
            [],               # merge
        ]

        merged = _try_consolidate(["ep1", "ep2"], mock_client)
        assert merged == 1

    def test_no_merge_when_no_overlap(self):
        from services.analysis_worker.app.analyzers.episode_builder import _try_consolidate

        mock_client = MagicMock()
        mock_client.run.return_value = [{"shared": 0}]

        merged = _try_consolidate(["ep1", "ep2"], mock_client)
        assert merged == 0
