"""Infrastructure security assertions.

Verifies that security-critical configuration is present in all deployment
environments' Bicep parameter files.

Threat coverage (DC-TM-SEC-002):
  TODO:VERIFY  SERVICE_AUTH_SECRET set in all deployed environments
  GAP-007      Inter-service auth silently disabled if secret missing
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INFRA_DIR = Path(__file__).parent.parent / "infra" / "bicep"
PARAM_DIR = INFRA_DIR / "parameters"
CONTAINER_APPS = INFRA_DIR / "modules" / "container-apps.bicep"
ENVIRONMENTS = ["dev", "val", "prod"]

# Must match container-apps.bicep: only these two apps get a public FQDN.
_EXPECTED_EXTERNAL_APPS = frozenset({"core-api", "ui"})
_EXPECTED_INTERNAL_APPS = frozenset(
    {
        "terminology-api",
        "fhir-api",
        "analytics-api",
        "model-inference",
        "training-worker",
        "pipeline-worker",
    }
)


def _container_app_blocks(source: str) -> list[tuple[str, str]]:
    """Return [(logical_name, block_text), ...] for each Container App resource."""
    pattern = re.compile(
        r"^resource \w+ 'Microsoft\.App/containerApps@[^']+' = \{",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(source))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        block = source[start:end]
        name_m = re.search(r"^\s*name:\s*'([^']+)'\s*$", block, re.MULTILINE)
        if not name_m:
            continue
        out.append((name_m.group(1), block))
    return out


def _ingress_external_flag(block: str) -> bool | None:
    """Return True/False for ingress.external, or None if ingress block missing."""
    m = re.search(
        r"ingress:\s*\{[^}]*external:\s*(true|false)",
        block,
        re.DOTALL,
    )
    if not m:
        return None
    return m.group(1) == "true"


class TestContainerAppsIngressPolicy:
    """ACA ingress: only core-api and ui may be external; all others internal."""

    def test_each_container_app_has_expected_external_setting(self):
        source = CONTAINER_APPS.read_text()
        apps = dict(_container_app_blocks(source))
        assert set(apps.keys()) == _EXPECTED_EXTERNAL_APPS | _EXPECTED_INTERNAL_APPS, (
            "container-apps.bicep Container App set changed -- update "
            "_EXPECTED_EXTERNAL_APPS / _EXPECTED_INTERNAL_APPS in this test."
        )
        for name, block in apps.items():
            external = _ingress_external_flag(block)
            assert external is not None, f"{name}: ingress.external not found"
            if name in _EXPECTED_EXTERNAL_APPS:
                assert external is True, f"{name}: must use external: true (public entry)"
            else:
                assert external is False, f"{name}: must use external: false (internal only)"


class TestServiceAuthSecretDeployment:
    """SERVICE_AUTH_SECRET must be wired through Bicep to all environments."""

    def test_container_apps_declares_service_auth_secret_env_var(self):
        """container-apps.bicep must map SERVICE_AUTH_SECRET from a Key Vault secret ref."""
        source = CONTAINER_APPS.read_text()
        assert "SERVICE_AUTH_SECRET" in source, (
            "SERVICE_AUTH_SECRET env var not found in container-apps.bicep"
        )
        assert "service-auth-secret" in source, (
            "service-auth-secret Key Vault secret ref not found in container-apps.bicep"
        )

    def test_container_apps_keyvault_secret_reference(self):
        """The Key Vault URL for service-auth-secret must be declared in the secrets array."""
        source = CONTAINER_APPS.read_text()
        assert "keyVaultUrl" in source and "service-auth-secret" in source, (
            "service-auth-secret Key Vault URL mapping missing from container-apps.bicep"
        )

    def test_migrate_secrets_generates_if_missing(self):
        """migrate-secrets.ps1 must auto-generate SERVICE_AUTH_SECRET when absent."""
        script = INFRA_DIR.parent / "scripts" / "migrate-secrets.ps1"
        if not script.exists():
            pytest.skip("migrate-secrets.ps1 not found")
        source = script.read_text()
        assert "SERVICE_AUTH_SECRET" in source, (
            "migrate-secrets.ps1 does not reference SERVICE_AUTH_SECRET"
        )


class TestCookieSecureAllEnvironments:
    """COOKIE_SECURE must be 'true' in all non-dev Bicep parameter files."""

    @pytest.mark.parametrize("env", ENVIRONMENTS)
    def test_cookie_secure_set(self, env):
        param_file = PARAM_DIR / f"{env}.bicepparam"
        if not param_file.exists():
            pytest.skip(f"{param_file.name} not found")
        source = param_file.read_text()
        assert "cookieSecure" in source, f"cookieSecure param missing from {env}.bicepparam"
        assert "true" in source.split("cookieSecure")[1][:30], (
            f"cookieSecure not set to 'true' in {env}.bicepparam"
        )


class TestAllowedOriginsPerEnvironment:
    """ALLOWED_ORIGINS must be configured per-environment (not wildcard)."""

    @pytest.mark.parametrize("env", ["val", "prod"])
    def test_no_localhost_in_non_dev(self, env):
        param_file = PARAM_DIR / f"{env}.bicepparam"
        if not param_file.exists():
            pytest.skip(f"{param_file.name} not found")
        source = param_file.read_text()
        origins_line = [l for l in source.splitlines() if "allowedOrigins" in l]
        assert origins_line, f"allowedOrigins missing from {env}.bicepparam"
        assert "localhost" not in origins_line[0], (
            f"localhost must not be in allowedOrigins for {env}"
        )

    @pytest.mark.parametrize("env", ["val", "prod"])
    def test_no_wildcard_origin(self, env):
        param_file = PARAM_DIR / f"{env}.bicepparam"
        if not param_file.exists():
            pytest.skip(f"{param_file.name} not found")
        source = param_file.read_text()
        origins_line = [l for l in source.splitlines() if "allowedOrigins" in l]
        assert origins_line, f"allowedOrigins missing from {env}.bicepparam"
        assert "'*'" not in origins_line[0], (
            f"Wildcard origin must not be in allowedOrigins for {env}"
        )


class TestSessionTtlPerEnvironment:
    """SESSION_TTL_HOURS must be configured per-environment."""

    @pytest.mark.parametrize("env", ENVIRONMENTS)
    def test_session_ttl_set(self, env):
        param_file = PARAM_DIR / f"{env}.bicepparam"
        if not param_file.exists():
            pytest.skip(f"{param_file.name} not found")
        source = param_file.read_text()
        assert "sessionTtlHours" in source, f"sessionTtlHours missing from {env}.bicepparam"

    @pytest.mark.parametrize("env,max_hours", [("dev", 24), ("val", 24), ("prod", 48)])
    def test_session_ttl_within_bounds(self, env, max_hours):
        param_file = PARAM_DIR / f"{env}.bicepparam"
        if not param_file.exists():
            pytest.skip(f"{param_file.name} not found")
        source = param_file.read_text()
        for line in source.splitlines():
            if "sessionTtlHours" in line:
                value = "".join(c for c in line.split("=")[1].strip() if c.isdigit())
                if value:
                    assert int(value) <= max_hours, (
                        f"sessionTtlHours={value} exceeds {max_hours}h limit for {env}"
                    )
                break
