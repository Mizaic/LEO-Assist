"""VT-LEO-AI-122 - Safety-net alert persistence + alert_id unification.

Covers TC-001..TC-006.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# persist_safety_net_alerts core behaviour
# ---------------------------------------------------------------------------


class _RecordingClient:
    """Minimal stand-in for PatientGraphClient.run that records calls."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.upsert_count = 0

    def run(self, query: str, **params):
        self.calls.append((query, dict(params)))
        if "MERGE (a:SafetyNetAlert {alert_id:" in query:
            self.upsert_count += 1
            return [{"alert_id": params["alert_id"]}]
        return []


def _signal(**overrides):
    base = {
        "patient_id": "pat-1",
        "episode_id": "ep-1",
        "type": "missing_safety_netting",
        "severity": "warning",
        "description": "No safety-netting recorded",
    }
    base.update(overrides)
    return base


def test_persist_creates_alert_and_patient_edge():
    """VT-122-TC-001."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        persist_safety_net_alerts,
    )

    client = _RecordingClient()
    result = persist_safety_net_alerts("pat-1", [_signal()], client)
    assert len(result) == 1
    queries = [q for q, _ in client.calls]
    assert any("HAS_SAFETY_NET_ALERT" in q for q in queries)
    assert any("alert_id: $alert_id" in q for q in queries)


def test_persist_links_episode_when_present():
    """VT-122-TC-002."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        persist_safety_net_alerts,
    )

    client = _RecordingClient()
    persist_safety_net_alerts("pat-1", [_signal()], client)
    queries = [q for q, _ in client.calls]
    assert any("FOR_EPISODE" in q for q in queries)


def test_persist_skips_episode_link_when_absent():
    """VT-122-TC-003."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        persist_safety_net_alerts,
    )

    client = _RecordingClient()
    sig = _signal(episode_id="")
    persist_safety_net_alerts("pat-1", [sig], client)
    queries = [q for q, _ in client.calls]
    assert not any("FOR_EPISODE" in q for q in queries)


def test_persist_is_idempotent():
    """VT-122-TC-004."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        persist_safety_net_alerts,
    )

    client = _RecordingClient()
    sig = _signal()
    first = persist_safety_net_alerts("pat-1", [sig], client)
    second = persist_safety_net_alerts("pat-1", [sig], client)
    assert first == second, "Deterministic alert_id must match across runs"


def test_persist_noop_when_patient_id_empty():
    """Guard clause: no writes without a patient_id."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        persist_safety_net_alerts,
    )

    client = _RecordingClient()
    result = persist_safety_net_alerts("", [_signal()], client)
    assert result == []
    assert client.calls == []


def test_derive_alert_id_stable():
    """Deterministic id seeded from patient+episode+type."""
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        _derive_alert_id,
    )

    a = _derive_alert_id(_signal())
    b = _derive_alert_id(_signal())
    assert a == b
    c = _derive_alert_id(_signal(type="excessive_referral_wait"))
    assert a != c


def test_derive_alert_id_preserves_existing():
    from services.analysis_worker.app.analyzers.safety_net_persistence import (
        _derive_alert_id,
    )

    explicit = _derive_alert_id({"alert_id": "already-set"})
    assert explicit == "already-set"


# ---------------------------------------------------------------------------
# Dashboards router -- canonical alert_id in MATCH/SELECT/SET
# ---------------------------------------------------------------------------


class TestAnalyticsRouterAlertIdCanonical:
    """VT-122-TC-005, TC-006."""

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_alerts_projection_uses_alert_id(self, MockPG):
        from services.analytics_api.app.routers.dashboards import safety_net_alerts

        MockPG.return_value.run.return_value = []
        safety_net_alerts(org_id=None)
        query = MockPG.return_value.run.call_args[0][0]
        assert "a.alert_id AS id" in query
        assert "a.id AS id" not in query

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_worklist_alerts_collection_uses_alert_id(self, MockPG):
        from services.analytics_api.app.routers.dashboards import safety_net_worklist

        MockPG.return_value.run.return_value = []
        safety_net_worklist(org_id=None)
        query = MockPG.return_value.run.call_args[0][0]
        assert "id: a.alert_id" in query
        assert "id: a.id," not in query

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_action_alert_matches_on_alert_id(self, MockPG):
        from services.analytics_api.app.routers.dashboards import (
            ActionAlertRequest,
            action_css_alert,
        )

        MockPG.return_value.run.return_value = [{"id": "a1"}]
        action_css_alert("a1", ActionAlertRequest(actioned=True))
        # Inspect every run() call made during this request.
        queries = [call.args[0] for call in MockPG.return_value.run.call_args_list]
        assert any("{alert_id: $aid}" in q for q in queries)
        assert not any("{id: $aid}" in q for q in queries)


# ---------------------------------------------------------------------------
# Subgraph wiring
# ---------------------------------------------------------------------------


@patch("services.analysis_worker.app.analyzers.safety_net_persistence.persist_safety_net_alerts")
@patch("libs.pipeline_graph.subgraphs.safety_net.detect_safety_net_signals")
@patch("libs.neo4j_client.client.KnowledgeGraphClient")
@patch("libs.neo4j_client.client.PatientGraphClient")
def test_subgraph_persists_detected_signals(
    mock_pg, mock_kg, mock_detect, mock_persist
):
    """VT-122-TC-007: safety_net subgraph invokes persist after detect."""
    # Re-import with patches active
    from importlib import reload

    import libs.pipeline_graph.subgraphs.safety_net as mod

    reload(mod)
    # The reloaded module re-binds names; use direct references
    mock_pg.return_value = MagicMock()
    mock_kg.return_value = MagicMock()
    mock_detect.return_value = [
        {
            "patient_id": "pat-1",
            "episode_id": "ep-1",
            "type": "missing_safety_netting",
            "severity": "warning",
            "description": "msg",
        }
    ]
    # Need to patch the now-reloaded symbol too
    with patch.object(mod, "persist_safety_net_alerts") as reloaded_persist, patch.object(
        mod, "detect_safety_net_signals", return_value=mock_detect.return_value
    ):
        state = {
            "patient_id": "pat-1",
            "episodes": [{"episode_id": "ep-1"}],
        }
        mod.detect_safety_net(state)
        assert reloaded_persist.called
        args, kwargs = reloaded_persist.call_args
        assert args[0] == "pat-1"
        assert args[1] == mock_detect.return_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
