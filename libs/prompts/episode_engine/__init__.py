"""Versioned prompts for the clinical episode engine.

Azure OpenAI GPT-5 is the primary provider. AWS Bedrock is optional. Prompt
contracts remain provider-neutral so routing can change without clinical drift.

Each stage has its own module with:
    SYSTEM           : str  -- prepended with INJECTION_GUARD
    USER_TEMPLATE    : str  -- format(...) template; arg names documented per file
    SCHEMA           : dict -- JSON Schema for structured tool output
    TOOL_NAME        : str  -- tool name for forced JSON
    VERSION          : str  -- "v1", "v2", ...

Bumping a prompt: copy the module to ``<stage>_v2.py`` and add a re-export
here. Old versions stay so historical traces remain reproducible.
"""

from libs.prompts.episode_engine import (
    audit_relevance_filter_v1,
    classifier_v1,
    milestone_extractor_v1,
    reconciler_v1,
    segmenter_v1,
)

__all__ = [
    "segmenter_v1",
    "classifier_v1",
    "milestone_extractor_v1",
    "reconciler_v1",
    "audit_relevance_filter_v1",
]
