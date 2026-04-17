"""SBAR (Situation, Background, Assessment, Recommendation) pipeline.

Modules:
  events            -- Pydantic contract for the pipeline-jobs queue payload
  source_resolver   -- Pulls text and SNOMED codes for Situation/Background sources
  assessment_formatter -- Deterministic narrative from /terminology/guidelines/evaluate
  prompt_calls      -- Wraps LLM calls for situation, background, recommendation

See ``services/pipeline_worker/app/services/sbar_orchestrator.py`` for the
end-to-end orchestration that consumes these helpers and persists the
:Assessment node.
"""
