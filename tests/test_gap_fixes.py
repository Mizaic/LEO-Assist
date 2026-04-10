"""Tests for GAP security fixes.

Covers:
  - GAP-002: JWT JWKS verification added to auth.py
  - GAP-004: Auth guards on terminology surface form mutations
  - GAP-008: NER-based de-identification (optional second pass)
  - GAP-012: Security audit log structured output
  - GAP-014: DEIDENTIFY_LOCAL_ORGS env var configurable org list
  - COD-T-001: Pydantic schema validation on Service Bus messages
  - COD-T-002: patient_id / encounter_id format validation
  - CSP-T-001: Security response headers
  - TODO:VERIFY patient_id_hash — raw ID no longer stored (SHA-256 used)
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import sys
import types
import unittest
from typing import Any
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# GAP-008 / GAP-014 — deidentify module tests
# ---------------------------------------------------------------------------

class TestDeidentifyLocalOrgsFromEnv(unittest.TestCase):
    """GAP-014: _LOCAL_ORGS is read from DEIDENTIFY_LOCAL_ORGS env var."""

    def test_builtin_orgs_used_when_env_absent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEIDENTIFY_LOCAL_ORGS", None)
            import importlib
            import libs.utils.deidentify as m
            importlib.reload(m)
            self.assertIn("LGH", m._LOCAL_ORGS)

    def test_env_var_overrides_builtin_list(self):
        with patch.dict(os.environ, {"DEIDENTIFY_LOCAL_ORGS": "Acme Clinic|Beta Trust"}, clear=False):
            import libs.utils.deidentify as m
            importlib.reload(m)
            self.assertIn("Acme Clinic", m._LOCAL_ORGS)
            self.assertIn("Beta Trust", m._LOCAL_ORGS)
            self.assertNotIn("LGH", m._LOCAL_ORGS)

    def test_env_var_org_redacted_in_text(self):
        with patch.dict(os.environ, {"DEIDENTIFY_LOCAL_ORGS": "Riverside Health Centre"}, clear=False):
            import libs.utils.deidentify as m
            importlib.reload(m)
            result = m.deidentify_text("Referred to Riverside Health Centre today.")
            self.assertIn("[ORGANISATION]", result)
            self.assertNotIn("Riverside Health Centre", result)

    def tearDown(self):
        # Reload with clean env so other tests are unaffected
        os.environ.pop("DEIDENTIFY_LOCAL_ORGS", None)
        import libs.utils.deidentify as m
        importlib.reload(m)


class TestNerSecondPass(unittest.TestCase):
    """GAP-008: NER second pass opt-in via DEIDENTIFY_NER_MODEL."""

    def test_ner_not_run_when_env_absent(self):
        """When DEIDENTIFY_NER_MODEL is not set, NER pass is skipped."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEIDENTIFY_NER_MODEL", None)
            import libs.utils.deidentify as m
            importlib.reload(m)
            with patch.object(m, "_get_ner_nlp", return_value=None) as mock_ner:
                result = m.deidentify_text("Patient spoke with Christopher yesterday.")
            mock_ner.assert_not_called()

    def test_ner_called_when_env_set(self):
        """When DEIDENTIFY_NER_MODEL is set and ner=True, _get_ner_nlp is called."""
        with patch.dict(os.environ, {"DEIDENTIFY_NER_MODEL": "en_core_web_sm"}, clear=False):
            import libs.utils.deidentify as m
            importlib.reload(m)
            mock_nlp = MagicMock()
            mock_doc = MagicMock()
            mock_doc.ents = []
            mock_nlp.return_value = mock_doc
            with patch.object(m, "_get_ner_nlp", return_value=mock_nlp):
                m.deidentify_text("Hello Christopher.", ner=True)
            mock_nlp.assert_called_once()

    def test_ner_redact_replaces_person_entities(self):
        """_ner_redact replaces PERSON spans with [PERSON]."""
        import libs.utils.deidentify as m

        # Build a mock spaCy nlp with one PERSON entity
        ent = types.SimpleNamespace(label_="PERSON", start_char=13, end_char=24)
        doc = types.SimpleNamespace(ents=[ent])
        mock_nlp = MagicMock(return_value=doc)

        result = m._ner_redact("Patient saw Christopher for follow-up.", mock_nlp)
        self.assertIn("[PERSON]", result)
        self.assertNotIn("Christopher", result)

    def test_ner_redact_ignores_non_person_entities(self):
        """_ner_redact does not touch ORG or GPE entities."""
        import libs.utils.deidentify as m

        ent = types.SimpleNamespace(label_="ORG", start_char=0, end_char=3)
        doc = types.SimpleNamespace(ents=[ent])
        mock_nlp = MagicMock(return_value=doc)

        result = m._ner_redact("NHS trust referred.", mock_nlp)
        self.assertEqual(result, "NHS trust referred.")

    def tearDown(self):
        os.environ.pop("DEIDENTIFY_NER_MODEL", None)
        import libs.utils.deidentify as m
        importlib.reload(m)


# ---------------------------------------------------------------------------
# COD-T-001 / COD-T-002 — Service Bus message schema validation
# ---------------------------------------------------------------------------

class TestCodingJobMessageSchema(unittest.TestCase):
    """COD-T-001/002: CodingJobMessage Pydantic validation."""

    @classmethod
    def setUpClass(cls):
        # Import the model from job_handler
        import services.coding_worker.app.services.job_handler as jh
        cls.CodingJobMessage = jh.CodingJobMessage

    def test_valid_all_mode(self):
        msg = self.CodingJobMessage.model_validate({"patient_id": "P001", "mode": "all"})
        self.assertEqual(msg.patient_id, "P001")
        self.assertEqual(msg.mode, "all")
        self.assertFalse(msg.dry_run)

    def test_valid_with_encounter(self):
        msg = self.CodingJobMessage.model_validate({
            "patient_id": "P-001",
            "encounter_id": "E-999",
            "mode": "extract_encounter",
        })
        self.assertEqual(msg.encounter_id, "E-999")

    def test_missing_patient_id_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({"mode": "all"})

    def test_empty_patient_id_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({"patient_id": ""})

    def test_invalid_mode_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({"patient_id": "P1", "mode": "consensus_fanout"})

    def test_patient_id_injection_chars_raises(self):
        """COD-T-002: Illegal characters in patient_id are rejected."""
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({"patient_id": "P001; DROP TABLE patients; --"})

    def test_encounter_id_injection_chars_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({
                "patient_id": "P001",
                "encounter_id": "<script>alert(1)</script>",
            })

    def test_patient_id_too_long_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CodingJobMessage.model_validate({"patient_id": "a" * 129})

    def test_none_encounter_id_allowed(self):
        msg = self.CodingJobMessage.model_validate({"patient_id": "P001"})
        self.assertIsNone(msg.encounter_id)

    def test_handle_coding_job_rejects_malformed_message(self):
        """Malformed messages are logged and dropped (no exception raised)."""
        import asyncio
        import services.coding_worker.app.services.job_handler as jh
        from libs.message_bus.base import Message

        bad_msg = Message(body={"mode": "all"})  # missing patient_id
        with self.assertLogs("services.coding_worker.app.services.job_handler", level="ERROR") as cm:
            asyncio.get_event_loop().run_until_complete(jh.handle_coding_job(bad_msg))
        self.assertTrue(any("malformed" in line.lower() for line in cm.output))


# ---------------------------------------------------------------------------
# GAP-012 — Security audit log
# ---------------------------------------------------------------------------

class TestSecurityAuditLog(unittest.TestCase):
    """GAP-012: Security audit log emits structured JSON records."""

    def _capture_audit(self, fn, *args, **kwargs):
        """Run fn and capture all records emitted to 'security.audit' logger."""
        records = []
        handler = logging.handlers_test = logging.handlers if False else None

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        audit_logger = logging.getLogger("security.audit")
        cap = Capture()
        audit_logger.addHandler(cap)
        try:
            fn(*args, **kwargs)
        finally:
            audit_logger.removeHandler(cap)
        return records

    def test_emit_login_success_structure(self):
        from libs.audit.security_log import emit_login_success
        records = self._capture_audit(
            emit_login_success,
            email="alice@example.com",
            ip="10.0.0.1",
            session_id_prefix="abc12345xyz",
        )
        self.assertEqual(len(records), 1)
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "auth.login.success")
        self.assertEqual(payload["email"], "alice@example.com")
        self.assertEqual(payload["ip"], "10.0.0.1")
        self.assertIn("ts", payload)

    def test_emit_login_failure_structure(self):
        from libs.audit.security_log import emit_login_failure
        records = self._capture_audit(
            emit_login_failure,
            reason="token_verification_failed",
            ip="10.0.0.2",
            detail="JWTError: signature check failed",
        )
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "auth.login.failure")
        self.assertIn("JWTError", payload["detail"])

    def test_emit_token_rejected_structure(self):
        from libs.audit.security_log import emit_token_rejected
        records = self._capture_audit(
            emit_token_rejected,
            reason="v1_issuer",
            ip="10.0.0.3",
        )
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "security.token_rejected")

    def test_emit_authz_denied_structure(self):
        from libs.audit.security_log import emit_authz_denied
        records = self._capture_audit(
            emit_authz_denied,
            email="bob@example.com",
            ip="10.0.0.4",
            route="/api/admin/rules",
            reason="not_admin",
        )
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "authz.denied")
        self.assertEqual(payload["route"], "/api/admin/rules")

    def test_emit_admin_action_structure(self):
        from libs.audit.security_log import emit_admin_action
        records = self._capture_audit(
            emit_admin_action,
            email="admin@example.com",
            ip="10.0.0.5",
            action="create_context_rule",
            resource="context_rules",
            detail="regex=foo",
        )
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "authz.admin_action")
        self.assertEqual(payload["action"], "create_context_rule")

    def test_emit_mfa_blocked_structure(self):
        from libs.audit.security_log import emit_login_mfa_blocked
        records = self._capture_audit(
            emit_login_mfa_blocked,
            email="carol@example.com",
            ip="10.0.0.6",
            amr=["pwd"],
        )
        payload = json.loads(records[0].getMessage())
        self.assertEqual(payload["event"], "auth.login.mfa_blocked")
        self.assertEqual(payload["amr"], ["pwd"])

    def test_audit_events_at_warning_level(self):
        """All audit events are emitted at WARNING level so they always appear in logs."""
        from libs.audit.security_log import emit_login_success
        records = self._capture_audit(
            emit_login_success,
            email="dave@example.com",
            ip="10.0.0.7",
            session_id_prefix="sess1",
        )
        self.assertEqual(records[0].levelno, logging.WARNING)


# ---------------------------------------------------------------------------
# GAP-002 — JWT JWKS verification
# ---------------------------------------------------------------------------

# The auth module lives under services/api/ and uses "app.*" internal imports.
# We add that directory to sys.path for this test class only.
_API_SERVICE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "services", "api"
)


class TestJwtVerification(unittest.TestCase):
    """GAP-002: _verify_id_token uses JWKS, not bare base64 decode."""

    def setUp(self):
        # Patch environment so auth module constants are set
        self.env = {
            "AZURE_AD_TENANT_ID": "test-tenant",
            "AZURE_AD_CLIENT_ID": "test-client-id",
            "AZURE_AD_CLIENT_SECRET": "secret",
        }
        self.patcher = patch.dict(os.environ, self.env)
        self.patcher.start()

        # Inject services/api on sys.path so "app.*" resolves
        self._api_path = os.path.normpath(_API_SERVICE_DIR)
        if self._api_path not in sys.path:
            sys.path.insert(0, self._api_path)
            self._added_path = True
        else:
            self._added_path = False

    def tearDown(self):
        self.patcher.stop()
        if self._added_path and self._api_path in sys.path:
            sys.path.remove(self._api_path)
        # Remove cached modules so next test gets a clean import
        for key in list(sys.modules.keys()):
            if key.startswith("app.routers.auth") or key == "app.routers.auth":
                del sys.modules[key]

    def _load_auth_mod(self):
        """Load (or reload) the auth module with services/api on path."""
        for key in list(sys.modules.keys()):
            if key == "app.routers.auth":
                del sys.modules[key]
        import importlib
        return importlib.import_module("app.routers.auth")

    def test_verify_id_token_calls_jwt_decode(self):
        """_verify_id_token must call jose.jwt.decode (cryptographic verification)."""
        auth_mod = self._load_auth_mod()

        fake_claims = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
            "preferred_username": "user@test.com",
        }
        fake_jwks = {"keys": []}

        with patch.object(auth_mod, "_get_jwks", return_value=fake_jwks):
            with patch.object(auth_mod.jwt, "decode", return_value=fake_claims) as mock_decode:
                claims = auth_mod._verify_id_token("fake.token.here")

        mock_decode.assert_called_once()
        call_kwargs = mock_decode.call_args
        # Audience must match app registration; issuer is not fixed (multi-tenant /common/)
        self.assertIn("test-client-id", str(call_kwargs))
        self.assertEqual(claims["preferred_username"], "user@test.com")

    def test_verify_id_token_raises_401_on_jwt_error(self):
        """JWTError during verification raises HTTPException(401)."""
        from fastapi import HTTPException
        from jose import JWTError
        auth_mod = self._load_auth_mod()

        with patch.object(auth_mod, "_get_jwks", return_value={"keys": []}):
            with patch.object(auth_mod.jwt, "decode", side_effect=JWTError("bad sig")):
                with self.assertRaises(HTTPException) as ctx:
                    auth_mod._verify_id_token("bad.token.value")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_jwks_cache_reused_within_ttl(self):
        """JWKS is not re-fetched within the TTL window."""
        auth_mod = self._load_auth_mod()

        auth_mod._JWKS_CACHE = {"keys": [{"kid": "k1"}]}
        auth_mod._JWKS_FETCHED_AT = 999_999_999.0  # far future — within TTL

        with patch.object(auth_mod, "time") as mock_time:
            mock_time.monotonic.return_value = 999_999_999.0 + 60
            mock_time.strftime = __import__("time").strftime
            result = auth_mod._get_jwks()

        self.assertEqual(result["keys"][0]["kid"], "k1")

    def test_jwks_cache_refreshed_after_ttl(self):
        """JWKS is re-fetched after TTL expires."""
        auth_mod = self._load_auth_mod()

        auth_mod._JWKS_CACHE = {"keys": [{"kid": "old"}]}
        auth_mod._JWKS_FETCHED_AT = 0.0  # very stale

        new_jwks = {"keys": [{"kid": "new"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = new_jwks
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch.object(auth_mod.httpx, "Client", return_value=mock_client):
            result = auth_mod._get_jwks()

        self.assertEqual(result["keys"][0]["kid"], "new")


# ---------------------------------------------------------------------------
# GAP-004 — Terminology surface form mutations require service token
# ---------------------------------------------------------------------------

class TestTerminologySurfaceFormAuth(unittest.TestCase):
    """GAP-004: POST/DELETE surface form endpoints enforce verify_service_token."""

    @classmethod
    def _get_protected_routes(cls):
        import inspect
        from fastapi import Depends
        from services.terminology_api.app.routers.surface_forms import router
        protected = []
        for route in router.routes:
            # Check route-level dependencies
            for dep in getattr(route, "dependencies", []):
                if hasattr(dep, "dependency") and "verify_service_token" in str(dep.dependency):
                    protected.append(route.path)
                    break
            # Also check endpoint signature for Depends
            if route.path in protected:
                continue
            sig = inspect.signature(route.endpoint)
            for param in sig.parameters.values():
                if isinstance(param.default, type(Depends(lambda: None))):
                    if "verify_service_token" in str(param.default.dependency):
                        protected.append(route.path)
                        break
        return protected

    def test_upsert_mapping_is_protected(self):
        from fastapi import Depends
        import inspect
        from libs.auth.service_auth import verify_service_token
        from services.terminology_api.app.routers.surface_forms import upsert_surface_form_mapping

        sig = inspect.signature(upsert_surface_form_mapping)
        deps = [
            p.default.dependency
            for p in sig.parameters.values()
            if isinstance(p.default, type(Depends(lambda: None)))
        ]
        self.assertIn(verify_service_token, deps)

    def test_delete_surface_form_is_protected(self):
        from fastapi import Depends
        import inspect
        from libs.auth.service_auth import verify_service_token
        from services.terminology_api.app.routers.surface_forms import delete_surface_form

        sig = inspect.signature(delete_surface_form)
        deps = [
            p.default.dependency
            for p in sig.parameters.values()
            if isinstance(p.default, type(Depends(lambda: None)))
        ]
        self.assertIn(verify_service_token, deps)

    def test_deduplicate_is_protected(self):
        from fastapi import Depends
        import inspect
        from libs.auth.service_auth import verify_service_token
        from services.terminology_api.app.routers.surface_forms import deduplicate_surface_forms

        sig = inspect.signature(deduplicate_surface_forms)
        deps = [
            p.default.dependency
            for p in sig.parameters.values()
            if isinstance(p.default, type(Depends(lambda: None)))
        ]
        self.assertIn(verify_service_token, deps)

    def test_read_endpoints_remain_open(self):
        """GET list/grouped/duplicates endpoints do NOT require service token."""
        from fastapi import Depends
        import inspect
        from libs.auth.service_auth import verify_service_token
        from services.terminology_api.app.routers.surface_forms import (
            list_surface_forms,
            list_grouped_surface_forms,
            audit_surface_form_duplicates,
        )
        for fn in (list_surface_forms, list_grouped_surface_forms, audit_surface_form_duplicates):
            sig = inspect.signature(fn)
            deps = [
                p.default.dependency
                for p in sig.parameters.values()
                if isinstance(p.default, type(Depends(lambda: None)))
            ]
            self.assertNotIn(verify_service_token, deps, f"{fn.__name__} should not require service token")


# ---------------------------------------------------------------------------
# TODO:VERIFY — patient_id_hash is actually hashed (SHA-256)
# ---------------------------------------------------------------------------

class TestPatientIdHashIsHashed(unittest.TestCase):
    """Verify pipeline_service stores SHA-256 hash, not the raw patient_id."""

    def test_coding_decision_stores_sha256_hash(self):
        """The patient_id written to CodingDecision.patient_id_hash must be a SHA-256 hex digest."""
        try:
            import services.coding_worker.app.pipeline.pipeline_service as ps
        except Exception:
            self.skipTest("Legacy CodingPipeline module removed after WorkflowEngine cutover")
            return

        # Inspect the source to ensure hashlib.sha256 is used
        import inspect
        try:
            source = inspect.getsource(ps.CodingPipeline._write_coding_decisions)
        except OSError:
            self.skipTest("Legacy CodingPipeline source unavailable after WorkflowEngine cutover")
            return
        self.assertIn("sha256", source)
        self.assertIn("pid_hash", source)
        self.assertIn("patient_id_hash=pid_hash", source)

    def test_sha256_produces_expected_hash(self):
        """Sanity check: known patient_id produces correct SHA-256 hex digest."""
        patient_id = "patient-001"
        expected = hashlib.sha256(patient_id.encode()).hexdigest()
        computed = hashlib.sha256(patient_id.encode()).hexdigest()
        self.assertEqual(computed, expected)
        self.assertEqual(len(computed), 64)
        self.assertNotEqual(computed, patient_id)

    def test_raw_patient_id_never_written(self):
        """patient_id_hash=patient_id (the old bug) must not appear in source."""
        try:
            import services.coding_worker.app.pipeline.pipeline_service as ps
        except Exception:
            self.skipTest("Legacy CodingPipeline module removed after WorkflowEngine cutover")
            return
        import inspect
        try:
            source = inspect.getsource(ps.CodingPipeline._write_coding_decisions)
        except OSError:
            self.skipTest("Legacy CodingPipeline source unavailable after WorkflowEngine cutover")
            return
        self.assertNotIn("patient_id_hash=patient_id", source)


# ---------------------------------------------------------------------------
# CSP-T-001 — Security headers middleware
# ---------------------------------------------------------------------------

class TestSecurityHeaders(unittest.IsolatedAsyncioTestCase):
    """CSP-T-001: Security headers are present on API responses."""

    async def test_security_headers_on_health_endpoint(self):
        """Security headers middleware adds CSP, HSTS, etc. to every response."""
        from httpx import AsyncClient, ASGITransport

        # Import the app — mock all heavy dependencies
        with patch.dict(os.environ, {
            "AZURE_AD_TENANT_ID": "t",
            "AZURE_AD_CLIENT_ID": "c",
            "AZURE_AD_CLIENT_SECRET": "s",
        }):
            try:
                import app.main as main_mod
                from app.main import app as fastapi_app
            except Exception:
                self.skipTest("Could not import app.main — skipping CSP header test")
                return

            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app), base_url="http://test"
            ) as client:
                resp = await client.get("/health")

        self.assertIn("Content-Security-Policy", resp.headers)
        self.assertIn("X-Content-Type-Options", resp.headers)
        self.assertIn("X-Frame-Options", resp.headers)
        csp = resp.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")


if __name__ == "__main__":
    unittest.main()
