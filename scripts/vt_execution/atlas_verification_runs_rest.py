"""Atlas verification-run REST helper.

Records a verification-test run and uploads evidence via the Atlas
verification-runs REST API.  Mirrors the pattern of the Playwright
atlas-validation-runs.ts helper so VT scripts can attach screenshots,
log snippets, or other artefacts alongside the pass/fail result.

Required environment variables:
    ATLAS_VERIFICATION_RUNS_BASE_URL
        e.g. https://atlas.healthcarecopilot.ai/api/qms-graph/api/v1/verification-runs
    ATLAS_ORGANIZATION_ID   -- tenant UUID
    QMS_SERVICE_TOKEN       -- service token with verification-runs scope

Optional:
    TEST_ENV                -- default environment label (default: local)

API contract (mirrors validation-runs):
    POST   {BASE}/                          create run -> { run_id }
    POST   {BASE}/{runId}/steps/{n}         record step result
    POST   {BASE}/{runId}/steps/{n}/evidence  upload evidence file
    PATCH  {BASE}/{runId}                   complete run
    GET    {BASE}/{runId}                   check run state

Usage from a pytest conftest or script::

    from scripts.vt_execution.atlas_verification_runs_rest import (
        VerificationRunClient, VerificationRunsNotConfigured,
    )

    client = VerificationRunClient.from_env()
    run_id = client.create_run(vt_id="<VT UUID>", executor="pytest")
    client.record_step(run_id, 0, "All assertions pass", "pass")
    client.upload_evidence(run_id, 0, b"<screenshot bytes>",
                           caption="pytest output", file_name="output.txt",
                           content_type="text/plain")
    client.complete(run_id, "pass", summary="5/5 assertions pass")
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_REQUIRED_ENV = (
    "ATLAS_VERIFICATION_RUNS_BASE_URL",
    "ATLAS_ORGANIZATION_ID",
    "QMS_SERVICE_TOKEN",
)


class VerificationRunsNotConfigured(RuntimeError):
    """Raised when a required env var is missing."""


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise VerificationRunsNotConfigured(
            f"Missing required env var: {name}. "
            "Set ATLAS_VERIFICATION_RUNS_BASE_URL, "
            "ATLAS_ORGANIZATION_ID, and QMS_SERVICE_TOKEN."
        )
    return val


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_multipart(fields: dict) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body_bytes, content_type_header)."""
    boundary = "VerificationEvidence----" + _sha256(str(fields).encode())[:16]
    parts: list[bytes] = []
    for name, value in fields.items():
        if isinstance(value, dict):
            # file field
            fname = value.get("filename", name)
            ctype = value.get("content_type", "application/octet-stream")
            data: bytes = value["data"]
            parts.append(
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{fname}"\r\n'
                f'Content-Type: {ctype}\r\n\r\n'.encode()
                + data
                + b'\r\n'
            )
        else:
            parts.append(
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n'.encode()
            )
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


@dataclass
class VerificationRunClient:
    base_url: str
    org_id: str
    token: str
    environment: str = "local"
    _ua: str = field(
        default=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        init=False,
        repr=False,
    )

    @classmethod
    def from_env(cls) -> "VerificationRunClient":
        """Build a client from environment variables."""
        for name in _REQUIRED_ENV:
            _require_env(name)
        return cls(
            base_url=os.environ["ATLAS_VERIFICATION_RUNS_BASE_URL"].rstrip("/"),
            org_id=os.environ["ATLAS_ORGANIZATION_ID"],
            token=os.environ["QMS_SERVICE_TOKEN"],
            environment=os.environ.get("TEST_ENV", "local"),
        )

    def _headers(self, content_type: Optional[str] = "application/json") -> dict:
        h = {
            "Authorization": f"Bearer {self.token}",
            "X-Organization-ID": self.org_id,
            "User-Agent": self._ua,
        }
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        content_type: Optional[str] = "application/json",
        timeout: int = 60,
    ) -> dict:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self._headers(content_type).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                if raw.strip():
                    return json.loads(raw)
                return {}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(
                f"Atlas verification-runs {method} {url}: "
                f"HTTP {e.code} {e.reason} -- {body_text}"
            ) from e

    def create_run(
        self,
        vt_id: str,
        executor: str = "pytest",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a verification run. Returns the run_id."""
        payload = {
            "vt_id": vt_id,
            "environment": self.environment,
            "executor": executor,
            "metadata": {
                "git_sha": os.environ.get("GITHUB_SHA"),
                **(metadata or {}),
            },
        }
        resp = self._request(
            "POST", "/", body=json.dumps(payload).encode()
        )
        run_id = resp.get("run_id")
        if not run_id:
            raise RuntimeError(
                f"create_run: no run_id in response: {resp}"
            )
        return run_id

    def record_step(
        self,
        run_id: str,
        step_index: int,
        step: str,
        result: str,
        notes: Optional[str] = None,
    ) -> None:
        """Record a single protocol step result (0-based step_index)."""
        payload: dict = {"step": step, "result": result}
        if notes:
            payload["notes"] = notes
        self._request(
            "POST",
            f"/{run_id}/steps/{step_index}",
            body=json.dumps(payload).encode(),
        )

    def upload_evidence(
        self,
        run_id: str,
        step_index: int,
        data: bytes,
        caption: Optional[str] = None,
        file_name: str = "evidence.png",
        content_type: str = "image/png",
    ) -> None:
        """Upload a screenshot or file as step evidence (multipart)."""
        fields: dict = {
            "file": {
                "filename": file_name,
                "content_type": content_type,
                "data": data,
            },
            "content_type": content_type,
            "sha256": _sha256(data),
        }
        if caption:
            fields["caption"] = caption
        body, ct_header = _build_multipart(fields)
        self._request(
            "POST",
            f"/{run_id}/steps/{step_index}/evidence",
            body=body,
            content_type=ct_header,
        )

    def complete(
        self,
        run_id: str,
        result: str,
        summary: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Complete the run (result: pass | fail | blocked | not_applicable)."""
        payload: dict = {
            "result": result,
            "completed_at": _utc_now(),
        }
        if summary:
            payload["summary"] = summary
        if failure_reason:
            payload["failure_reason"] = failure_reason
        self._request(
            "PATCH", f"/{run_id}", body=json.dumps(payload).encode()
        )

    def check_status(self, run_id: str) -> dict:
        """Return the current run status dict."""
        return self._request("GET", f"/{run_id}")

    def ensure_not_left_running(
        self,
        run_id: Optional[str],
        last_completed_step: int,
    ) -> None:
        """Safety cleanup: fail-complete any run still in 'running' state."""
        if not run_id:
            return
        try:
            status = self.check_status(run_id)
        except Exception:
            return
        if status.get("status") == "running":
            self.complete(
                run_id,
                result="fail",
                failure_reason=(
                    f"Suite ended without completing the verification run. "
                    f"Last completed step: {last_completed_step}."
                ),
            )


def is_configured() -> bool:
    """Return True when all required env vars are set (CI-safe guard)."""
    return all(os.environ.get(n, "").strip() for n in _REQUIRED_ENV)
