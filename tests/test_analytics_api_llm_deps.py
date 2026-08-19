"""Guard that the analytics image can import the shared LLM client.

The analytics API Dockerfile installs only
``services/analytics_api/requirements.txt``. Importing
``libs.llm_client`` (via encounter query understanding) requires
``jsonschema`` at module load.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_analytics_api_requirements_include_jsonschema() -> None:
    content = (REPO_ROOT / "services/analytics_api/requirements.txt").read_text()
    assert "jsonschema" in content, (
        "jsonschema must be in services/analytics_api/requirements.txt. "
        "The analytics image installs only this file, and "
        "libs.llm_client.json_helper imports jsonschema at module load."
    )
