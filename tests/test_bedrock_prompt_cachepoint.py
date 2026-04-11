from __future__ import annotations

from pathlib import Path


def test_bedrock_converse_sets_cachepoint_marker() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "libs" / "llm_client" / "factory.py").read_text(
        encoding="utf-8"
    )

    assert '{"cachePoint": {"type": "default"}}' in source
