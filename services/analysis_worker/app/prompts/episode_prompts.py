"""Prompts for episode builder and consolidator.

These are hardcoded fallbacks; FHIR Device resources can override them
via get_agent_prompt('episode-builder', 'agent-system-prompt').

Now re-exported from the central prompt registry (libs/prompts/).
"""
from libs.prompts.registry import get_prompt

EPISODE_BUILDER_SYSTEM = get_prompt("episode_builder_system", version=1)
EPISODE_BUILDER_TASK = get_prompt("episode_builder_task", version=1)
EPISODE_CONSOLIDATION_SYSTEM = get_prompt("episode_consolidation_system", version=1)
EPISODE_CONSOLIDATION_TASK = get_prompt("episode_consolidation_task", version=1)
