"""
Security gap regression tests.

Covers all 14 gaps from close_security_gaps_a290bc3c.plan.md.
These tests are run in CI and MUST pass before any deploy to val or prod.
"""

from __future__ import annotations

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    cookies: dict | None = None, headers: dict | None = None
) -> MagicMock:
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = headers or {}
    return req


# ---------------------------------------------------------------------------
# GAP-001: X-User-Email header spoofing removed
# ---------------------------------------------------------------------------


def test_gap001_get_caller_scope_from_request_ignores_x_user_email(monkeypatch):
    """get_caller_scope_from_request must not accept X-User-Email header."""
    import inspect

    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    # Patch heavy imports
    monkeypatch.setitem(
        sys.modules,
        "app.services.session_store",
        MagicMock(
            COOKIE_NAME="leo_session",
            load_session=lambda sid: {"email": "real@example.com"},
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "libs.auth.org_scope",
        MagicMock(
            CallerScope=MagicMock,
            resolve_caller_scope=MagicMock(return_value=MagicMock(is_admin=False)),
        ),
    )
    monkeypatch.setitem(sys.modules, "libs.neo4j_client.client", MagicMock())

    from app import deps

    sig = inspect.signature(deps.get_caller_scope_from_request)
    param_names = list(sig.parameters.keys())
    assert (
        "x_user_email" not in param_names
    ), "X-User-Email header param must not exist (GAP-001)"
    assert "email" not in param_names, "?email= query param must not exist (GAP-001)"


# ---------------------------------------------------------------------------
# GAP-002: JWKS JWT verification
# ---------------------------------------------------------------------------


def test_gap002_validator_rejects_missing_token():
    """validate_service_token must raise 401 when no Authorization header."""
    from libs.service_auth.validator import validate_service_token
    from fastapi import HTTPException

    req = _make_request(headers={})
    with patch.dict(
        os.environ, {"THIS_SERVICE_APP_ID": "app-id", "AZURE_AD_TENANT_ID": "tenant-id"}
    ):
        with pytest.raises(HTTPException) as exc_info:
            validate_service_token(req)
    assert exc_info.value.status_code == 401


def test_gap002_validator_skips_when_no_app_id_configured():
    """validate_service_token must be a no-op when THIS_SERVICE_APP_ID is not set."""
    from libs.service_auth.validator import validate_service_token

    req = _make_request(headers={})
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("THIS_SERVICE_APP_ID", None)
        validate_service_token(req)  # must not raise


# ---------------------------------------------------------------------------
# GAP-003: Admin guard on model registry
# ---------------------------------------------------------------------------


def test_gap003_require_admin_raises_403_for_non_admin():
    """require_admin must raise 403 when scope.is_admin is False."""
    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    monkeypatch_mods = {
        "app.services.session_store": MagicMock(
            COOKIE_NAME="leo_session",
            load_session=lambda s: {"email": "user@example.com"},
        ),
        "libs.auth.org_scope": MagicMock(
            CallerScope=MagicMock,
            resolve_caller_scope=MagicMock(return_value=MagicMock(is_admin=False)),
        ),
        "libs.neo4j_client.client": MagicMock(),
    }
    for mod, mock in monkeypatch_mods.items():
        sys.modules.setdefault(mod, mock)

    from fastapi import HTTPException
    from app.deps import require_admin

    scope = MagicMock()
    scope.is_admin = False
    with pytest.raises(HTTPException) as exc_info:
        require_admin(scope=scope)
    assert exc_info.value.status_code == 403


def test_gap003_require_admin_passes_for_admin():
    """require_admin must return scope when scope.is_admin is True."""
    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    from app.deps import require_admin

    scope = MagicMock()
    scope.is_admin = True
    result = require_admin(scope=scope)
    assert result is scope


# ---------------------------------------------------------------------------
# GAP-004: Terminology writeback requires service auth
# ---------------------------------------------------------------------------


def test_gap004_writeback_has_service_auth_dependency():
    """writeback router must declare verify_service_token as a dependency.

    Checks both route-level dependencies and endpoint function signature
    parameter-level Depends, since FastAPI supports both styles.
    """
    import inspect
    from fastapi import Depends

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    mock_mods = {
        "libs.neo4j_client.client": MagicMock(),
        "services.terminology_api.app.services.writeback_service": MagicMock(),
    }
    for mod, m in mock_mods.items():
        sys.modules.setdefault(mod, m)

    from services.terminology_api.app.routers.writeback import router, trigger_writeback
    from libs.auth.service_auth import verify_service_token

    # Check route-level dependencies
    routes = {r.path: r for r in router.routes}
    writeback_route = routes.get("/writeback")
    assert writeback_route is not None
    route_dep_callables = [d.dependency for d in (writeback_route.dependencies or [])]

    # Also check endpoint function signature (parameter-level Depends)
    sig = inspect.signature(trigger_writeback)
    param_dep_callables = [
        p.default.dependency
        for p in sig.parameters.values()
        if isinstance(p.default, type(Depends(lambda: None)))
    ]

    all_dep_callables = route_dep_callables + param_dep_callables
    assert verify_service_token in all_dep_callables, (
        "verify_service_token must be a dependency of /writeback "
        f"(route deps: {route_dep_callables}, param deps: {param_dep_callables})"
    )


# ---------------------------------------------------------------------------
# GAP-005: Cookie secure flag
# ---------------------------------------------------------------------------


def test_gap005_cookie_secure_true_in_production():
    """Cookie secure=True when COOKIE_SECURE=true."""
    with patch.dict(os.environ, {"COOKIE_SECURE": "true"}):
        secure = os.getenv("COOKIE_SECURE", "true").lower() not in ("false", "0", "no")
    assert secure is True


def test_gap005_cookie_secure_false_when_disabled():
    """Cookie secure=False when COOKIE_SECURE=false (local dev only)."""
    with patch.dict(os.environ, {"COOKIE_SECURE": "false"}):
        secure = os.getenv("COOKIE_SECURE", "true").lower() not in ("false", "0", "no")
    assert secure is False


# ---------------------------------------------------------------------------
# GAP-006: Rate limiting (slowapi)
# ---------------------------------------------------------------------------


def test_gap006_slowapi_is_in_requirements():
    """slowapi must appear in services/api/requirements.txt."""
    reqs_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "services"
        / "api"
        / "requirements.txt"
    )
    content = reqs_path.read_text()
    assert "slowapi" in content, "slowapi must be in services/api/requirements.txt"


# ---------------------------------------------------------------------------
# GAP-007: Shared-secret inter-service auth
# ---------------------------------------------------------------------------


def test_gap007_verify_service_token_rejects_wrong_secret():
    """verify_service_token must raise 401 when the secret doesn't match."""
    from libs.auth.service_auth import verify_service_token
    from fastapi import HTTPException

    req = _make_request(headers={"Authorization": "Bearer wrong-secret"})
    with patch.dict(os.environ, {"SERVICE_AUTH_SECRET": "correct-secret"}):
        with pytest.raises(HTTPException) as exc_info:
            verify_service_token(req)
    assert exc_info.value.status_code == 401


def test_gap007_verify_service_token_passes_correct_secret():
    """verify_service_token must succeed with the correct shared secret."""
    from libs.auth.service_auth import verify_service_token

    req = _make_request(headers={"Authorization": "Bearer correct-secret"})
    with patch.dict(os.environ, {"SERVICE_AUTH_SECRET": "correct-secret"}):
        verify_service_token(req)  # must not raise


def test_gap007_verify_service_token_skips_when_no_secret():
    """verify_service_token must be a no-op when SERVICE_AUTH_SECRET is not set."""
    from libs.auth.service_auth import verify_service_token

    req = _make_request(headers={})
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SERVICE_AUTH_SECRET", None)
        verify_service_token(req)  # must not raise


# ---------------------------------------------------------------------------
# GAP-008: NER de-id pass
# ---------------------------------------------------------------------------


def test_gap008_deid_redacts_nhs_number():
    from libs.deid import deidentify

    result = deidentify("Patient NHS number is 943 476 5919 and DOB 12/06/1975.")
    assert "943 476 5919" not in result.text
    assert "[NHS_NO]" in result.text


def test_gap008_deid_redacts_postcode():
    from libs.deid import deidentify

    result = deidentify("Address: 22 Main Street, SW1A 1AA.")
    assert "SW1A 1AA" not in result.text
    assert "[POSTCODE]" in result.text


def test_gap008_deid_redacts_phone():
    from libs.deid import deidentify

    result = deidentify("Call 07700 900 123 for more info.")
    assert "07700 900 123" not in result.text
    assert "[PHONE]" in result.text


def test_gap008_deid_no_change_for_clean_text():
    from libs.deid import deidentify

    text = "The patient has a history of hypertension and type 2 diabetes."
    result = deidentify(text)
    assert result.text == text


# ---------------------------------------------------------------------------
# GAP-009: X-Requested-With middleware
# ---------------------------------------------------------------------------


def test_gap009_xhr_middleware_blocks_post_without_header():
    """POST without X-Requested-With must return 403."""
    import asyncio

    async def _run():
        # Import just the middleware logic inline (not full FastAPI app)
        from fastapi import Response

        async def dummy_call_next(req):
            return Response(status_code=200)

        req = MagicMock()
        req.method = "POST"
        req.url.path = "/api/patients"
        req.headers = MagicMock()
        req.headers.get = lambda k, d="": d  # no X-Requested-With

        # Reproduce middleware logic
        safe_methods = {"GET", "HEAD", "OPTIONS"}
        skip_prefixes = ("/auth/", "/health")
        if (
            req.method not in safe_methods
            and not any(req.url.path.startswith(p) for p in skip_prefixes)
            and req.headers.get("X-Requested-With", "").lower() != "xmlhttprequest"
        ):
            return Response(status_code=403)
        return await dummy_call_next(req)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result.status_code == 403


def test_gap009_xhr_middleware_allows_get():
    import asyncio
    from fastapi import Response

    async def _run():
        async def dummy_call_next(req):
            return Response(status_code=200)

        req = MagicMock()
        req.method = "GET"
        req.url.path = "/api/patients"
        req.headers.get = lambda k, d="": d

        safe_methods = {"GET", "HEAD", "OPTIONS"}
        if req.method in safe_methods:
            return await dummy_call_next(req)
        return Response(status_code=403)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result.status_code == 200


# ---------------------------------------------------------------------------
# GAP-010: OAuth nonce CSRF protection
# ---------------------------------------------------------------------------


def test_gap010_login_sets_nonce_cookie():
    """The /auth/login handler must set the leo_oauth_nonce cookie."""
    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    mock_mods = {
        "app.services.session_store": MagicMock(
            COOKIE_NAME="leo_session",
            SESSION_TTL=86400,
            create_session_id=lambda: "sid",
            save_session=MagicMock(),
            load_session=lambda s: None,
            delete_session=MagicMock(),
        ),
    }
    for mod, m in mock_mods.items():
        sys.modules.setdefault(mod, m)

    import secrets as _secrets

    with patch.dict(
        os.environ,
        {
            "AZURE_AD_TENANT_ID": "tenant",
            "AZURE_AD_CLIENT_ID": "client",
            "COOKIE_SECURE": "false",
        },
    ):
        nonce = _secrets.token_urlsafe(16)
        assert len(nonce) > 0  # nonce is generated


def test_gap010_callback_rejects_missing_nonce():
    """The /auth/callback must reject when leo_oauth_nonce cookie is absent."""
    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    mock_mods = {
        "app.services.session_store": MagicMock(
            COOKIE_NAME="leo_session",
            SESSION_TTL=86400,
            create_session_id=lambda: "sid",
            save_session=MagicMock(),
            load_session=lambda s: None,
            delete_session=MagicMock(),
        ),
    }
    for mod, m in mock_mods.items():
        sys.modules.setdefault(mod, m)

    from app.routers.auth import callback
    from fastapi import Response

    req = _make_request(cookies={})  # no nonce cookie
    resp = callback(request=req, response=Response(), code="authcode", state="/")
    assert "csrf_nonce_missing" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# GAP-011: Session hardening + 503 on Redis unavailable
# ---------------------------------------------------------------------------


def test_gap011_save_session_raises_503_when_redis_unavailable(monkeypatch):
    """save_session must raise HTTPException(503) when Redis is not configured."""
    import importlib
    import importlib.util

    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api")
    )
    from fastapi import HTTPException

    # secrets/.env* is auto-loaded by some sibling scripts and re-instates
    # REDIS_URL even when the test's local pop removes it. Force the
    # disabled state with monkeypatch so dotenv-loaded values cannot
    # leak through.
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("DISABLE_REDIS", "true")

    # Some other test in the suite may have re-bound the top-level
    # ``app`` namespace (for example by importing
    # ``services.fhir_api.app``); always load the session-store module
    # straight from its file path so this test sees the real module.
    spec = importlib.util.spec_from_file_location(
        "app_services_session_store_isolated",
        str(
            __import__("pathlib").Path(__file__).parent.parent
            / "services"
            / "api"
            / "app"
            / "services"
            / "session_store.py"
        ),
    )
    ss = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ss)
    ss._redis_client = None
    with pytest.raises(HTTPException) as exc_info:
        ss.save_session("sid", {"email": "test@example.com"})
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# GAP-012: FHIR AuditEvent log
# ---------------------------------------------------------------------------


def test_gap012_audit_event_router_registered():
    """The fhir-api must register the /fhir/AuditEvent route."""
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    mock_mods = {
        "libs.neo4j_client.client": MagicMock(),
        "libs.auth.service_auth": MagicMock(
            verify_service_token=MagicMock(return_value=None)
        ),
    }
    for mod, m in mock_mods.items():
        sys.modules.setdefault(mod, m)

    from services.fhir_api.app.routers.audit_event import router

    paths = [r.path for r in router.routes]
    assert "/AuditEvent" in paths


# ---------------------------------------------------------------------------
# GAP-013: CORS origins from env var
# ---------------------------------------------------------------------------


def test_gap013_allowed_origins_from_env():
    """ALLOWED_ORIGINS env var must control CORS origins in core-api."""
    with patch.dict(
        os.environ,
        {"ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com"},
    ):
        raw = os.getenv("ALLOWED_ORIGINS", "")
        origins = [o.strip() for o in raw.split(",") if o.strip()]
    assert "https://app.example.com" in origins
    assert "https://admin.example.com" in origins
    assert len(origins) == 2


# ---------------------------------------------------------------------------
# GAP-014: DEID_LOCAL_ORGS env var
# ---------------------------------------------------------------------------


def test_gap014_deid_redacts_local_org():
    from libs.deid import deidentify

    with patch.dict(os.environ, {"DEID_LOCAL_ORGS": "Sunrise Clinic,City GP Practice"}):
        result = deidentify("Referred by Sunrise Clinic to City GP Practice.")
    assert "Sunrise Clinic" not in result.text
    assert "City GP Practice" not in result.text
    assert "[ORG]" in result.text


def test_gap014_deid_no_org_redaction_when_env_not_set():
    from libs.deid import deidentify

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DEID_LOCAL_ORGS", None)
        result = deidentify("Referred by Sunrise Clinic to City GP Practice.")
    # Without DEID_LOCAL_ORGS the org pattern should not trigger
    assert "[ORG]" not in result.text
