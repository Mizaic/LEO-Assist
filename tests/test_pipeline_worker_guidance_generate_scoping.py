"""Regression coverage for scoping ``POST /guidance/generate`` to a subset
of recommendations.

Atlas trace:
  DI: DI-53973180 (Generate Candidate Appropriateness Rule)
  DO: DO-F8C56339 (Rule generation, review, and edit surface)
  VT: VT-3804621E (Verify LLM rule generation produces pending-review
      candidates)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-53973180")

Bug fixed
---------
``RecommendationPickerDialog`` lets an admin select a subset of
recommendations and calls ``POST /api/guidance/rules/generate`` with
``recommendation_ids``. The Core API router forwards this to the pipeline
worker's ``POST /guidance/generate``. The worker's request model,
background-job launcher, and thread kwargs silently dropped
``recommendation_ids`` -- so selecting "just rule 1.1" generated candidate
rules for every normative recommendation in the guideline instead.

These tests pin the fix: the field survives request parsing, the endpoint
forwards it into the background thread, and the thread target forwards it
into ``GuidanceRuleGenerator.generate_rules_for_guideline``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.pipeline_worker.app.main import (
    GuidanceGenerateRequest,
    _run_guidance_generation,
    guidance_generate,
)


class TestGuidanceGenerateRequestModel:
    def test_accepts_recommendation_ids(self):
        req = GuidanceGenerateRequest(
            guideline_id="NG12",
            recommendation_ids=["NG12:v1:CH000:R000"],
        )
        assert req.recommendation_ids == ["NG12:v1:CH000:R000"]

    def test_recommendation_ids_defaults_to_none(self):
        req = GuidanceGenerateRequest(guideline_id="NG12")
        assert req.recommendation_ids is None


class TestGuidanceGenerateEndpointForwardsSelection:
    """POST /guidance/generate must pass recommendation_ids into the job."""

    @pytest.mark.asyncio
    async def test_thread_receives_recommendation_ids(self):
        body = GuidanceGenerateRequest(
            guideline_id="NG12",
            recommendation_ids=["NG12:v1:CH000:R000"],
        )
        with (
            patch("services.pipeline_worker.app.main._guidance_generate_jobs", {}),
            patch(
                "services.pipeline_worker.app.main.threading.Thread"
            ) as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            await guidance_generate(body)

        _, kwargs = mock_thread_cls.call_args
        assert kwargs["kwargs"]["recommendation_ids"] == ["NG12:v1:CH000:R000"]
        mock_thread.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_thread_receives_none_when_no_selection_made(self):
        """A full-guideline generation (no picker filter) still passes None
        explicitly, so downstream code never has to guess a default."""
        body = GuidanceGenerateRequest(guideline_id="NG12")
        with (
            patch("services.pipeline_worker.app.main._guidance_generate_jobs", {}),
            patch(
                "services.pipeline_worker.app.main.threading.Thread"
            ) as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            await guidance_generate(body)

        _, kwargs = mock_thread_cls.call_args
        assert kwargs["kwargs"]["recommendation_ids"] is None


class TestRunGuidanceGenerationForwardsSelection:
    """The background thread target must scope the generator call."""

    def test_forwards_recommendation_ids_to_generator(self):
        jobs = {"job-1": {"status": "running", "rule_ids": [], "error": None}}
        mock_generator = MagicMock()
        mock_generator.generate_rules_for_guideline.return_value = ["rule:1"]
        generator_cls_path = (
            "services.pipeline_worker.app.services.guidance_rule_generator"
            ".GuidanceRuleGenerator"
        )

        with (
            patch("services.pipeline_worker.app.main._guidance_generate_jobs", jobs),
            patch(
                "libs.neo4j_client.client.KnowledgeGraphClient"
            ) as mock_kg_client_cls,
            patch(generator_cls_path, return_value=mock_generator),
        ):
            mock_kg_client_cls.return_value = MagicMock()

            _run_guidance_generation(
                "job-1",
                "NG12",
                only_without_rules=False,
                recommendation_ids=["NG12:v1:CH000:R000"],
            )

        mock_generator.generate_rules_for_guideline.assert_called_once_with(
            "NG12",
            only_without_rules=False,
            recommendation_ids=["NG12:v1:CH000:R000"],
        )
        assert jobs["job-1"]["status"] == "done"
        assert jobs["job-1"]["rule_ids"] == ["rule:1"]
