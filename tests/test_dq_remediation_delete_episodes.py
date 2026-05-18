"""Tests for libs.dq.remediation.delete_episodes (unreviewed filter + params)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.dq import remediation as rem


@patch("libs.neo4j_client.client.run_with_retry")
def test_delete_episodes_preview_passes_unreviewed_only(mock_run: MagicMock) -> None:
    mock_run.return_value = [{"ep_count": 2}]
    client = MagicMock()
    rem.delete_episodes(
        client, status="review", site="Colorectal", unreviewed_only=True, dry_run=True
    )
    call = mock_run.call_args
    assert "reviewed_at IS NULL" in call.args[1]
    assert call.kwargs == {
        "status": "review",
        "site": "Colorectal",
        "unreviewed_only": True,
    }


@patch("libs.neo4j_client.client.run_with_retry")
def test_delete_episodes_defaults_unreviewed_only_false(mock_run: MagicMock) -> None:
    mock_run.return_value = [{"ep_count": 0}]
    rem.delete_episodes(MagicMock(), dry_run=True)
    assert mock_run.call_args.kwargs.get("unreviewed_only") is False


@patch("libs.neo4j_client.client.run_with_retry")
def test_delete_episodes_apply_uses_unreviewed_on_both_round_trips(
    mock_run: MagicMock,
) -> None:
    mock_run.side_effect = [[{"ep_count": 1}], []]
    rem.delete_episodes(MagicMock(), unreviewed_only=True, dry_run=False)
    assert mock_run.call_count == 2
    for c in mock_run.call_args_list:
        assert c.kwargs.get("unreviewed_only") is True
