"""Run the real form-schema router for one Playwright journey request.

Only the large language model detector and the graph are replaced:

- detect returns the heading-only sections given in the request, as the
  model does for a letter with admin sections;
- the graph has no other taught forms;
- save_form_schema stores nothing and echoes the schema back.

The skip-box fill, the request checks and the save check run for real.

Reads one JSON request on stdin:
    {"method": "POST" | "PUT", "path": "/form-schemas/...",
     "body": {...}, "detected": [...]}
and writes {"status": int, "body": ...} as the last line on stdout.

Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[4]
for _path in (ROOT, ROOT / "services" / "api"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_session_data  # noqa: E402
from app.routers.form_schema import router  # noqa: E402
from libs.llm_client.form_detection import FormDetection  # noqa: E402
from libs.pipeline.form_schema_normalizer import FormSchema  # noqa: E402
from libs.pipeline.form_schema_store import FormSchemaWrite  # noqa: E402

_ROUTER = "app.routers.form_schema"
_SESSION = {
    "email": "validation@example.com",
    "selected_role": "validation",
    "allowed_roles": ["validation"],
    "is_platform_admin": False,
}


def _echo_save(_client: object, write: FormSchemaWrite) -> FormSchema:
    return FormSchema(
        schema_id="val-" + write.fingerprint,
        fingerprint=write.fingerprint,
        form_name=write.form_name,
        sections=write.sections,
        created_by=write.created_by,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: _SESSION
    return TestClient(app)


def handle(request: dict) -> dict:
    """Send *request* through the real router and return status and body."""
    graph = MagicMock()
    graph.run.return_value = []
    with (
        patch(f"{_ROUTER}.PatientGraphClient", return_value=graph),
        patch(
            f"{_ROUTER}.detect_form_schema",
            return_value=FormDetection(sections=request["detected"]),
        ),
        patch(f"{_ROUTER}.save_form_schema", side_effect=_echo_save),
    ):
        resp = _client().request(
            request["method"], request["path"], json=request.get("body")
        )
    return {"status": resp.status_code, "body": resp.json()}


if __name__ == "__main__":
    reply = handle(json.loads(sys.stdin.read()))
    sys.stdout.write("\n" + json.dumps(reply, ensure_ascii=True) + "\n")
