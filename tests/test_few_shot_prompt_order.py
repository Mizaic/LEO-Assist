"""Ordering of dynamic few-shot examples inside the extraction user message.

Current practice is ascending relevance: the strongest example sits
immediately before the query so its pattern is freshest when the model
starts generating. The selector ranks best-first, so the renderer is
responsible for the flip.
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs._extractor import _build_relevant_examples_block
from libs.prompts.few_shot_config import FewShotSelectionConfig

_RANKED = [
    {"category": "labs", "description": "strongest", "input": "a", "output": "1"},
    {"category": "labs", "description": "middle", "input": "b", "output": "2"},
    {"category": "labs", "description": "weakest", "input": "c", "output": "3"},
]


def _descriptions(block: str) -> list[str]:
    return [
        line.split("- ", 1)[1].strip()
        for line in block.splitlines()
        if line.startswith("# ") and "- " in line
    ]


def test_default_order_is_unchanged_best_first() -> None:
    block = _build_relevant_examples_block(_RANKED)

    assert _descriptions(block) == ["strongest", "middle", "weakest"]


def test_ascending_order_puts_strongest_closest_to_the_query() -> None:
    block = _build_relevant_examples_block(
        _RANKED,
        config=FewShotSelectionConfig.disabled().replace(ascending_prompt_order=True),
    )

    assert _descriptions(block) == ["weakest", "middle", "strongest"]


def test_ordering_does_not_drop_or_duplicate_examples() -> None:
    block = _build_relevant_examples_block(
        _RANKED,
        config=FewShotSelectionConfig.disabled().replace(ascending_prompt_order=True),
    )

    assert sorted(_descriptions(block)) == ["middle", "strongest", "weakest"]
