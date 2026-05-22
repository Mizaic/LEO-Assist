"""Tests for terminology administrator audit log.

Atlas trace:
  VT-CE12337D -- Verify terminology administrator actions are recorded in audit log
    DO-669D6A69 -- Terminology administrator audit log
    DI-2AD4CCC3 -- Maintain audit log of terminology administrator actions

AC1: Every terminology sync trigger, load completion, load failure, and
     configuration change is recorded with user, timestamp, package,
     action type, and outcome.
AC2: Audit log entries are immutable once written.
AC3: Administrators can retrieve audit log entries for a given time period
     from the admin UI or API.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_audit_log():
    """Reset the audit log between tests."""
    from services.api.app.services.terminology_audit import clear_for_testing
    clear_for_testing()
    yield
    clear_for_testing()


# ---------------------------------------------------------------------------
# AC1: entries recorded with required fields
# ---------------------------------------------------------------------------


class TestAuditEntryContents:
    """AC1: Every action is recorded with all required fields."""

    def test_write_entry_contains_required_fields(self):
        """AC1: write_entry records user, timestamp, action_type, packages, outcome."""
        from services.api.app.services.terminology_audit import write_entry, ACTION_SYNC_TRIGGER

        entry = write_entry(
            user="admin@example.com",
            action_type=ACTION_SYNC_TRIGGER,
            packages=["snomed", "dmd"],
            outcome="in_progress",
            detail="phases=[1, 2, 3]",
        )

        assert entry["user"] == "admin@example.com"
        assert entry["action_type"] == ACTION_SYNC_TRIGGER
        assert entry["packages"] == ["snomed", "dmd"]
        assert entry["outcome"] == "in_progress"
        assert entry["detail"] == "phases=[1, 2, 3]"
        assert "timestamp" in entry
        assert "id" in entry

    def test_timestamp_is_iso8601(self):
        """AC1: timestamp is a valid ISO 8601 string."""
        from services.api.app.services.terminology_audit import write_entry, ACTION_SYNC_COMPLETE

        entry = write_entry(
            user="admin@example.com",
            action_type=ACTION_SYNC_COMPLETE,
            packages=["snomed"],
            outcome="success",
        )
        # Must parse without error
        dt = datetime.fromisoformat(entry["timestamp"])
        assert dt.tzinfo is not None

    def test_sync_trigger_action_recorded(self):
        """AC1: Sync trigger is recorded with action_type sync_trigger."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="u", action_type=ACTION_SYNC_TRIGGER, packages=["snomed"], outcome="in_progress")
        entries = get_entries()

        assert len(entries) == 1
        assert entries[0]["action_type"] == ACTION_SYNC_TRIGGER

    def test_sync_complete_action_recorded(self):
        """AC1: Successful sync records sync_complete."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_COMPLETE,
        )

        write_entry(user="u", action_type=ACTION_SYNC_COMPLETE, packages=["snomed"], outcome="success")
        entries = get_entries()

        assert entries[0]["action_type"] == ACTION_SYNC_COMPLETE
        assert entries[0]["outcome"] == "success"

    def test_sync_error_action_recorded(self):
        """AC1: Failed sync records sync_error with failure detail."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_ERROR,
        )

        write_entry(
            user="u",
            action_type=ACTION_SYNC_ERROR,
            packages=["dmd"],
            outcome="error",
            detail="Download/extract failed: Connection refused",
        )
        entries = get_entries()

        assert entries[0]["action_type"] == ACTION_SYNC_ERROR
        assert entries[0]["outcome"] == "error"
        assert "Connection refused" in entries[0]["detail"]

    def test_multiple_entries_all_retained(self):
        """AC1: All actions across a sync lifecycle are retained."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries,
            ACTION_SYNC_TRIGGER, ACTION_SYNC_COMPLETE,
        )

        write_entry(user="u", action_type=ACTION_SYNC_TRIGGER, packages=["snomed"], outcome="in_progress")
        write_entry(user="u", action_type=ACTION_SYNC_COMPLETE, packages=["snomed"], outcome="success")

        entries = get_entries()
        assert len(entries) == 2

    def test_invalid_action_type_raises(self):
        """AC1: write_entry rejects unknown action types."""
        from services.api.app.services.terminology_audit import write_entry

        with pytest.raises(ValueError, match="Invalid action_type"):
            write_entry(user="u", action_type="bogus", packages=[], outcome="unknown")


# ---------------------------------------------------------------------------
# AC2: entries are immutable once written
# ---------------------------------------------------------------------------


class TestAuditImmutability:
    """AC2: Audit log entries are immutable once written."""

    def test_returned_entry_is_a_copy(self):
        """AC2: Modifying the returned dict does not affect the stored entry."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        entry = write_entry(user="u", action_type=ACTION_SYNC_TRIGGER, packages=["snomed"], outcome="x")
        entry["user"] = "MUTATED"
        entry["outcome"] = "MUTATED"

        stored = get_entries()[0]
        assert stored["user"] == "u"
        assert stored["outcome"] == "x"

    def test_get_entries_returns_copies(self):
        """AC2: Modifying a retrieved entry does not affect subsequent reads."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="u", action_type=ACTION_SYNC_TRIGGER, packages=["snomed"], outcome="ok")

        first_read = get_entries()
        first_read[0]["outcome"] = "MUTATED"

        second_read = get_entries()
        assert second_read[0]["outcome"] == "ok"

    def test_packages_list_is_a_copy(self):
        """AC2: Mutating the packages list in a retrieved entry does not affect the store."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="u", action_type=ACTION_SYNC_TRIGGER, packages=["snomed"], outcome="ok")
        get_entries()[0]["packages"].append("INJECTED")

        assert get_entries()[0]["packages"] == ["snomed"]


# ---------------------------------------------------------------------------
# AC3: entries retrievable by time period
# ---------------------------------------------------------------------------


class TestAuditRetrieval:
    """AC3: Administrators can retrieve entries for a given time period."""

    def test_get_entries_returns_all_when_no_filter(self):
        """AC3: get_entries() with no args returns all entries."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="a", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="x")
        write_entry(user="b", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="y")

        assert len(get_entries()) == 2

    def test_get_entries_since_filters_old(self):
        """AC3: since= excludes entries with earlier timestamps."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="early", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="ok")
        cutoff = datetime.now(timezone.utc).isoformat()
        time.sleep(0.01)
        write_entry(user="late", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="ok")

        entries = get_entries(since=cutoff)
        assert len(entries) == 1
        assert entries[0]["user"] == "late"

    def test_get_entries_until_filters_new(self):
        """AC3: until= excludes entries with later timestamps."""
        from services.api.app.services.terminology_audit import (
            write_entry, get_entries, ACTION_SYNC_TRIGGER,
        )

        write_entry(user="early", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="ok")
        cutoff = datetime.now(timezone.utc).isoformat()
        time.sleep(0.01)
        write_entry(user="late", action_type=ACTION_SYNC_TRIGGER, packages=[], outcome="ok")

        entries = get_entries(until=cutoff)
        assert len(entries) == 1
        assert entries[0]["user"] == "early"

    def test_get_entries_empty_when_no_writes(self):
        """AC3: get_entries() returns empty list when nothing has been logged."""
        from services.api.app.services.terminology_audit import get_entries

        assert get_entries() == []


# ---------------------------------------------------------------------------
# Integration: router wires audit on sync events
# ---------------------------------------------------------------------------


class TestSyncWithAuditIntegration:
    """AC1: Sync trigger and completion are written via run_sync_with_audit."""

    def test_successful_sync_writes_sync_complete_entry(self):
        """AC1: A successful sync writes a sync_complete audit entry."""
        from services.api.app.services.terminology_audit import (
            get_entries, run_sync_with_audit,
        )
        import queue as q
        from pathlib import Path

        events: q.Queue = q.Queue()
        mock_full_sync = MagicMock(return_value=None)

        run_sync_with_audit("tester@example.com", ["snomed"], {1, 2}, events, mock_full_sync, Path("."))

        entries = get_entries()
        action_types = [e["action_type"] for e in entries]
        assert "sync_complete" in action_types

        complete = next(e for e in entries if e["action_type"] == "sync_complete")
        assert complete["user"] == "tester@example.com"
        assert complete["packages"] == ["snomed"]
        assert complete["outcome"] == "success"

    def test_failed_sync_writes_sync_error_entry(self):
        """AC1: A failed sync writes a sync_error entry with the failure detail."""
        from services.api.app.services.terminology_audit import (
            get_entries, run_sync_with_audit,
        )
        import queue as q
        from pathlib import Path

        events: q.Queue = q.Queue()
        mock_full_sync = MagicMock(side_effect=RuntimeError("Neo4j loader crashed"))

        run_sync_with_audit("tester@example.com", ["snomed"], {1}, events, mock_full_sync, Path("."))

        entries = get_entries()
        error_entries = [e for e in entries if e["action_type"] == "sync_error"]
        assert error_entries, "Expected a sync_error audit entry"
        assert "Neo4j loader crashed" in error_entries[0]["detail"]
        assert error_entries[0]["outcome"] == "error"
