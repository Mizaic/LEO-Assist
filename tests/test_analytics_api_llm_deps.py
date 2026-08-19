"""Guard that service images can import the shared LLM client.

Each service Dockerfile installs only its own requirements.txt, then
copies ``libs/``. Importing ``libs.llm_client`` (even for prompt safety)
loads ``json_helper``, which imports ``jsonschema`` at module load.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Services whose runtime code imports libs.llm_client and whose image
# installs only that service's requirements.txt.
REQUIREMENTS_FILES = (
    "services/analytics_api/requirements.txt",
    "services/terminology_api/requirements.txt",
    "services/api/requirements.txt",
    "services/pipeline_worker/requirements.txt",
)


@pytest.mark.parametrize("relative_path", REQUIREMENTS_FILES)
def test_llm_client_images_include_jsonschema(relative_path: str) -> None:
    requirements_path = REPO_ROOT / relative_path
    assert requirements_path.exists(), f"missing {relative_path}"
    content = requirements_path.read_text()
    assert "jsonschema" in content, (
        f"jsonschema must be in {relative_path}. "
        "The image installs only this file, and "
        "libs.llm_client.json_helper imports jsonschema at module load."
    )
