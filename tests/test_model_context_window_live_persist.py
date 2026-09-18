"""Live persist: record each model's context window on its ModelConfig.

ModelConfig is the surface that owns model configuration, but it only
ever carried prices and a model id. Nothing in the graph said how much
any model could read, so every budget in the platform was a number
somebody typed and nobody could check.

The published limits live in ``libs.llm_client.context_budget``, which is
the authoring source. This writes them onto the matching ModelConfig rows
so an operator can see the limit their budgets are measured against.

Opt-in:

  LIVE_NEO4J_MODELS=1 pytest tests/test_model_context_window_live_persist.py -v

Rule: .cursor/rules/architecture-first.mdc -- ModelConfig owns model
configuration, so the window belongs on ModelConfig.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

from libs.llm_client.context_budget import window_for_model

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_NEO4J_MODELS") != "1",
    reason="Set LIVE_NEO4J_MODELS=1 to write context windows to ModelConfig.",
)

_WRITE = """
MATCH (m:ModelConfig {key: $key})
SET m.context_window_tokens = $total,
    m.max_input_tokens = $max_input,
    m.max_output_tokens = $max_output,
    m.usable_input_tokens = $usable_input,
    m.usable_output_tokens = $usable_output,
    m.updated_at = datetime()
RETURN m.key AS key, m.context_window_tokens AS total
"""


@pytest.fixture(scope="module")
def driver():
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    drv = GraphDatabase.driver(
        os.environ["PROD_NEO4J_URI"],
        auth=(os.environ["PROD_NEO4J_USER"], os.environ["PROD_NEO4J_PASSWORD"]),
    )
    yield drv
    drv.close()


def test_every_model_config_row_carries_its_window(driver) -> None:
    with driver.session() as session:
        rows = session.run(
            "MATCH (m:ModelConfig) RETURN m.key AS key, m.model_id AS model_id"
        ).data()
        assert rows, "no ModelConfig rows to write to"

        for row in rows:
            window = window_for_model(row["model_id"])
            written = session.run(
                _WRITE,
                key=row["key"],
                total=window.context_window_tokens,
                max_input=window.max_input_tokens,
                max_output=window.max_output_tokens,
                usable_input=window.usable_input_tokens,
                usable_output=window.usable_output_tokens,
            ).single()
            assert written is not None, row["key"]
            assert written["total"] == window.context_window_tokens

        missing = session.run(
            "MATCH (m:ModelConfig) WHERE m.context_window_tokens IS NULL "
            "RETURN count(m) AS n"
        ).single()["n"]
        assert missing == 0
