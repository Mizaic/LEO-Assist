"""Security tests for the post-processor/context rule management endpoints.

These endpoints live in app.routers.context_and_ignore_rules (split out of
the former training.py god-file in the 2026-07 CTO peer-review item 2:
core-api router decomposition -- pure move, no behaviour change).

Covers:
- _validate_regex: valid patterns, syntax errors, length limit, ReDoS probing
- POST /post-processor-rules: requires admin, validates context_regex
- PATCH /post-processor-rules/{rule_id}: requires admin
- POST /context-rules: requires admin, enforces literal length, uses scope.email
- PATCH /context-rules/{rule_id}/deactivate: requires admin
- Route dependency inspection: verify require_admin is wired in correctly

Threat coverage (DC-TM-SEC-002):
  GAP-015  User-configurable rules without change control or injection controls
  GAP-016  ReDoS via user-supplied regex patterns
"""

from __future__ import annotations

import re
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Import _validate_regex with all heavy deps mocked out
# ---------------------------------------------------------------------------


def _import_validate_regex():
    """Return the _validate_regex function from app.routers.context_and_ignore_rules.

    Mocks all module-level imports that require live services (Neo4j, auth,
    cypher queries, etc.) so the function can be tested in isolation without
    network access.
    """
    heavy_mocks = {
        "libs.auth.org_scope": MagicMock(
            CallerScope=MagicMock,
            get_caller_scope=MagicMock(),
        ),
        "libs.neo4j_client.client": MagicMock(),
        "libs.cypher.coding_review_queries": MagicMock(),
        "libs.cypher.surface_form_task_queries": MagicMock(),
        "libs.cypher.post_processor_rule_queries": MagicMock(),
        "services.terminology_api.app.queries.terminology": MagicMock(),
        "app.deps": MagicMock(require_admin=MagicMock()),
    }
    for mod, mock in heavy_mocks.items():
        sys.modules.setdefault(mod, mock)

    # Force re-import if already cached from a different test
    sys.modules.pop("app.routers.context_and_ignore_rules", None)
    sys.path.insert(
        0,
        str(__import__("pathlib").Path(__file__).parent.parent / "services" / "api"),
    )

    from app.routers.context_and_ignore_rules import _validate_regex

    return _validate_regex


# ---------------------------------------------------------------------------
# _validate_regex — unit tests
# ---------------------------------------------------------------------------


class TestValidateRegex:

    @pytest.fixture(autouse=True)
    def fn(self):
        self._validate_regex = _import_validate_regex()

    def test_valid_simple_pattern_passes(self):
        self._validate_regex(r"\bcough\b")  # must not raise

    def test_valid_complex_pattern_passes(self):
        self._validate_regex(r"(?:type\s+[12]|T2DM|T1DM)")  # must not raise

    def test_empty_pattern_passes(self):
        # Empty pattern is valid regex in Python
        self._validate_regex("")  # must not raise

    def test_invalid_regex_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex("[unclosed bracket")
        assert exc_info.value.status_code == 422
        assert "Invalid regex" in exc_info.value.detail

    def test_pattern_over_max_length_raises_422(self):
        pattern = "a" * 201
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex(pattern, max_length=200)
        assert exc_info.value.status_code == 422
        assert "200" in exc_info.value.detail

    def test_pattern_exactly_at_max_length_passes(self):
        pattern = "a" * 200
        self._validate_regex(pattern, max_length=200)  # must not raise

    def test_redos_pattern_raises_422(self):
        """A classically catastrophic email-validation-style regex triggers the ReDoS probe."""
        # This pattern requires an uppercase letter to match; applied to an all-lowercase probe
        # it causes exponential backtracking (verified to take >4s in Python 3.11+).
        # Pattern source: OWASP ReDoS catalogue (email-like validation anti-pattern).
        redos_pattern = r"^(([a-zA-Z])+.)+[A-Z]([a-zA-Z])+$"
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex(redos_pattern)
        assert exc_info.value.status_code == 422
        assert "backtracking" in exc_info.value.detail.lower()

    def test_anchored_greedy_redos_raises_422(self):
        """Another anchored greedy pattern that causes catastrophic backtracking."""
        redos_pattern = r"^(a+)*b$"
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex(redos_pattern)
        assert exc_info.value.status_code == 422

    def test_benign_clinical_regex_passes(self):
        self._validate_regex(r"(?i)type\s*2\s*diabet")  # must not raise

    def test_anchored_regex_passes(self):
        self._validate_regex(r"^hypertension$")  # must not raise

    def test_custom_max_length_enforced(self):
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex("abc", max_length=2)
        assert exc_info.value.status_code == 422

    def test_syntax_error_detail_contains_regex_message(self):
        with pytest.raises(HTTPException) as exc_info:
            self._validate_regex("(?P<name>")
        assert "Invalid regex" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Route dependency inspection — admin guards wired correctly
# ---------------------------------------------------------------------------


class TestRouteAdminDependencies:
    """Verify that admin-only mutation routes declare require_admin as a dependency."""

    @pytest.fixture(autouse=True)
    def router(self):
        heavy_mocks = {
            "libs.auth.org_scope": MagicMock(
                CallerScope=MagicMock,
                get_caller_scope=MagicMock(),
            ),
            "libs.neo4j_client.client": MagicMock(),
            "libs.cypher.coding_review_queries": MagicMock(),
            "libs.cypher.surface_form_task_queries": MagicMock(),
            "libs.cypher.post_processor_rule_queries": MagicMock(),
            "services.terminology_api.app.queries.terminology": MagicMock(),
        }
        for mod, mock in heavy_mocks.items():
            sys.modules.setdefault(mod, mock)

        # Provide a real require_admin that we can look for in dependencies
        from fastapi import Depends

        real_require_admin = MagicMock(__name__="require_admin")
        mock_deps = MagicMock(require_admin=real_require_admin)
        sys.modules["app.deps"] = mock_deps

        sys.modules.pop("app.routers.context_and_ignore_rules", None)
        sys.path.insert(
            0,
            str(
                __import__("pathlib").Path(__file__).parent.parent / "services" / "api"
            ),
        )

        from app.routers.context_and_ignore_rules import router as rules_router

        self._router = rules_router
        self._require_admin = real_require_admin

    def _has_admin(self, path: str, method: str) -> bool:
        """Check whether require_admin appears as a route-level or parameter dependency.

        `path` is the mounted path (e.g. "/training/context-rules"); the
        sub-router itself carries no prefix, so it is stripped before
        matching against `route.path`.
        """
        import inspect
        from fastapi import params as fastapi_params

        bare_path = path.removeprefix("/training")
        for route in self._router.routes:
            if route.path != bare_path:
                continue
            if method.upper() not in getattr(route, "methods", set()):
                continue

            # 1. Explicit route-level dependencies (Depends in @router.post(dependencies=[...]))
            if self._require_admin in [d.dependency for d in route.dependencies]:
                return True

            # 2. Parameter-level dependencies (scope: CallerScope = Depends(require_admin))
            try:
                sig = inspect.signature(route.endpoint)
                for param in sig.parameters.values():
                    if (
                        isinstance(param.default, fastapi_params.Depends)
                        and param.default.dependency is self._require_admin
                    ):
                        return True
            except (ValueError, TypeError):
                pass

        return False

    def test_post_processor_rules_post_requires_admin(self):
        assert self._has_admin(
            "/training/post-processor-rules", "POST"
        ), "POST /training/post-processor-rules must require admin (GAP-015)"

    def test_post_processor_rules_patch_requires_admin(self):
        assert self._has_admin(
            "/training/post-processor-rules/{rule_id}", "PATCH"
        ), "PATCH /training/post-processor-rules/{rule_id} must require admin (GAP-015)"

    def test_context_rules_post_requires_admin(self):
        assert self._has_admin(
            "/training/context-rules", "POST"
        ), "POST /training/context-rules must require admin (GAP-015)"

    def test_context_rules_deactivate_patch_requires_admin(self):
        assert self._has_admin(
            "/training/context-rules/{rule_id}/deactivate", "PATCH"
        ), "PATCH /training/context-rules/{rule_id}/deactivate must require admin (GAP-015)"

    def test_context_rules_get_does_not_require_admin(self):
        """GET is read-only; admin guard is not required."""
        assert not self._has_admin("/training/context-rules", "GET")

    def test_post_processor_rules_get_does_not_require_admin(self):
        assert not self._has_admin("/training/post-processor-rules", "GET")


# ---------------------------------------------------------------------------
# Context rule creation — functional security checks
# ---------------------------------------------------------------------------


class TestContextRuleSecurityChecks:
    """Test validation logic in create_context_rule without a live FastAPI app."""

    def _get_create_fn(self):
        """Import create_context_rule with all heavy deps mocked."""
        _import_validate_regex()  # ensures sys.path and mocks are set up
        from app.routers.context_and_ignore_rules import create_context_rule

        return create_context_rule

    def test_empty_literal_raises_422(self):
        fn = self._get_create_fn()
        body = MagicMock(
            literal="   ", category="NEGATED_EXISTENCE", direction="FORWARD"
        )
        scope = MagicMock(is_admin=True, email="admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            fn(body=body, scope=scope)
        assert exc_info.value.status_code == 422

    def test_literal_over_200_chars_raises_422(self):
        fn = self._get_create_fn()
        body = MagicMock(
            literal="a" * 201, category="NEGATED_EXISTENCE", direction="FORWARD"
        )
        scope = MagicMock(is_admin=True, email="admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            fn(body=body, scope=scope)
        assert exc_info.value.status_code == 422
        assert "200" in exc_info.value.detail

    def test_invalid_category_raises_422(self):
        fn = self._get_create_fn()
        body = MagicMock(literal="no evidence", category="MADE_UP", direction="FORWARD")
        scope = MagicMock(is_admin=True, email="admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            fn(body=body, scope=scope)
        assert exc_info.value.status_code == 422

    def test_invalid_direction_raises_422(self):
        fn = self._get_create_fn()
        body = MagicMock(
            literal="no evidence", category="NEGATED_EXISTENCE", direction="SIDEWAYS"
        )
        scope = MagicMock(is_admin=True, email="admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            fn(body=body, scope=scope)
        assert exc_info.value.status_code == 422

    def test_created_by_uses_scope_email_not_body(self):
        """created_by must come from the verified session, not the request body."""
        fn = self._get_create_fn()

        captured_kwargs = {}
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)

        def capture_run(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        mock_session.run = capture_run
        mock_client = MagicMock()
        mock_client.session.return_value = mock_session

        with patch(
            "app.routers.context_and_ignore_rules.PatientGraphClient",
            return_value=mock_client,
        ):
            body = MagicMock(
                literal="no evidence of",
                category="NEGATED_EXISTENCE",
                direction="FORWARD",
                max_scope=6,
                created_by="attacker@evil.com",  # attacker-supplied value
            )
            scope = MagicMock(is_admin=True, email="real-admin@nhs.uk")
            fn(body=body, scope=scope)

        assert (
            captured_kwargs.get("created_by") == "real-admin@nhs.uk"
        ), "created_by must use scope.email, not body.created_by (audit trail)"
        assert captured_kwargs.get("created_by") != "attacker@evil.com"
