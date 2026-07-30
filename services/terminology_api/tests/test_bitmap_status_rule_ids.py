"""bitmap/status returns rule_ids from the active compiled ruleset.

Atlas: DI-EB716E68 / VT-C6B93AF0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.terminology_api.app.routers.guidelines import bitmap_status


def test_bitmap_status_includes_rule_ids_from_active_ruleset() -> None:
    store = MagicMock()
    store.get_current_ruleset.return_value = {
        "version": "v1",
        "rules": [
            {"rule_id": "rule-a"},
            {"id": "rule-b"},
            {"rule_id": ""},
            "skip-me",
        ],
        "compile_timestamp": "2026-07-01T00:00:00Z",
        "scope_type": "global",
        "scope_id": "default",
        "policy_mode": "advisory",
        "compile_stats": {},
    }
    with patch(
        "services.terminology_api.app.routers.guidelines.BitmapStore",
        return_value=store,
    ):
        result = bitmap_status(scope_type="global", scope_id="default")

    assert result["active_version"] == "v1"
    assert result["rule_count"] == 4
    assert result["rule_ids"] == ["rule-a", "rule-b"]


def test_bitmap_status_empty_rule_ids_when_no_ruleset() -> None:
    store = MagicMock()
    store.get_current_ruleset.return_value = None
    with patch(
        "services.terminology_api.app.routers.guidelines.BitmapStore",
        return_value=store,
    ):
        result = bitmap_status(scope_type="global", scope_id="default")

    assert result["active_version"] is None
    assert result["rule_ids"] == []
