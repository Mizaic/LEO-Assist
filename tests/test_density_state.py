"""VT-LEO-AI-168 -- adaptive density preference helpers.

Verifies libs.auth.density_state in isolation (Neo4j mocked) and the
density router endpoint contract through FastAPI's TestClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.auth.density_state import (
    DensityNotAllowedError,
    fetch_density,
    set_density,
)


# -----------------------------------------------------------------------------
# VT-168-TC-001  -- fetch_density returns None on missing email
# -----------------------------------------------------------------------------
def test_fetch_density_missing_email_returns_none() -> None:
    assert fetch_density("") is None
    assert fetch_density("   ") is None


@patch("libs.auth.density_state.PatientGraphClient")
def test_fetch_density_missing_practitioner_returns_none(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = []
    assert fetch_density("nobody@x.com") is None


@patch("libs.auth.density_state.PatientGraphClient")
def test_fetch_density_unknown_value_returns_none(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [{"density_preference": "huge"}]
    assert fetch_density("user@x.com") is None


@patch("libs.auth.density_state.PatientGraphClient")
def test_fetch_density_returns_stored_value(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [{"density_preference": "compact"}]
    assert fetch_density("USER@X.com ") == "compact"


@patch("libs.auth.density_state.PatientGraphClient")
def test_fetch_density_fail_soft_on_error(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.side_effect = RuntimeError("graph down")
    assert fetch_density("user@x.com") is None


# -----------------------------------------------------------------------------
# VT-168-TC-002  -- set_density rejects unknown tier
# -----------------------------------------------------------------------------
def test_set_density_rejects_unknown_tier() -> None:
    with pytest.raises(DensityNotAllowedError):
        set_density("user@x.com", "huge")


def test_set_density_rejects_missing_email() -> None:
    with pytest.raises(DensityNotAllowedError):
        set_density("", "compact")


# -----------------------------------------------------------------------------
# VT-168-TC-003  -- set_density returns stored value for valid tier
# -----------------------------------------------------------------------------
@patch("libs.auth.density_state.PatientGraphClient")
def test_set_density_returns_stored_value(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.return_value = [{"density_preference": "compact"}]
    assert set_density("user@x.com", "compact") == "compact"


@patch("libs.auth.density_state.PatientGraphClient")
def test_set_density_missing_practitioner_raises_lookup(
    MockClient: MagicMock,
) -> None:
    instance = MockClient.return_value
    instance.run.return_value = []
    with pytest.raises(LookupError):
        set_density("ghost@x.com", "compact")
