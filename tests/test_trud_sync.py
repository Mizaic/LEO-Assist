"""Tests for TRUD sync fail-safe and staleness checks.

Atlas trace:
  VT-2FD319AA -- Verify failed terminology sync preserves previous knowledge graph
    DO-84D554EA -- Fail-safe TRUD sync (services/api/app/services/trud_sync.py)
    DI-698EE6EE -- Preserve approved terminology on load failure

  VT-16BF8B33 -- Verify terminology staleness comparison and admin alert
    DO-16C2E440 -- TRUD package staleness check (services/api/app/services/trud_sync.py)
    DI-81022210 -- Alert administrators when terminology is out of date
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# VT-2FD319AA: fail-safe on load failure
# ---------------------------------------------------------------------------


class TestTrudSyncFailSafe:
    """Verify failed terminology sync preserves previous knowledge graph.

    AC1: When a TRUD API call fails, full_sync emits sync_error and stops
         without writing to the knowledge graph.
    AC2: When a download fails, full_sync emits sync_error and stops.
    AC3: When the loader phase fails, full_sync emits sync_error and stops.
    AC4: The sync_error event contains a human-readable failure reason.
    """

    def _run_sync(self, packages, emit, *, api_ok=True, download_ok=True, loader_ok=True):
        from services.api.app.services.trud_sync import full_sync

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp)

            def fake_get_release(item_id):
                if not api_ok:
                    return None
                return {
                    "name": "SNOMEDCT2_41.5.0_20260211000001",
                    "archiveFileUrl": "https://example.com/snomed.zip",
                    "archiveFileSizeBytes": 1024,
                    "releaseDate": "2026-02-11",
                }

            def fake_download(url, dest, emit_fn):
                if not download_ok:
                    raise OSError("Connection refused")
                dest.write_bytes(b"PK\x03\x04")  # minimal zip header

            def fake_extract(zip_path, dest_dir, emit_fn):
                dest_dir.mkdir(parents=True, exist_ok=True)

            def fake_loader(external_path, phases, emit_fn):
                if not loader_ok:
                    raise RuntimeError("Neo4j loader phase failed")

            with (
                patch("services.api.app.services.trud_sync.get_trud_release", side_effect=fake_get_release),
                patch("services.api.app.services.trud_sync._download_file", side_effect=fake_download),
                patch("services.api.app.services.trud_sync._extract_snomed", side_effect=fake_extract),
                patch("services.api.app.services.trud_sync._run_loader", side_effect=fake_loader),
            ):
                full_sync(external, ["snomed"], {1, 2, 3}, emit)

    def test_ac1_trud_api_failure_emits_sync_error(self):
        """AC1: TRUD API unreachable -> sync_error emitted, no KG write."""
        events = []
        self._run_sync(["snomed"], events.append, api_ok=False)

        error_events = [e for e in events if e.get("type") == "sync_error"]
        assert error_events, "Expected at least one sync_error event"
        assert "sync_done" not in {e.get("type") for e in events}

    def test_ac1_sync_error_contains_reason(self):
        """AC4: sync_error event contains a human-readable failure reason."""
        events = []
        self._run_sync(["snomed"], events.append, api_ok=False)

        error_events = [e for e in events if e.get("type") == "sync_error"]
        assert error_events[0].get("msg"), "sync_error must have a non-empty msg"

    def test_ac2_download_failure_emits_sync_error(self):
        """AC2: Download failure -> sync_error emitted, sync aborts."""
        events = []
        self._run_sync(["snomed"], events.append, api_ok=True, download_ok=False)

        error_events = [e for e in events if e.get("type") == "sync_error"]
        assert error_events, "Expected sync_error on download failure"
        assert "sync_done" not in {e.get("type") for e in events}

    def test_ac3_loader_failure_emits_sync_error(self):
        """AC3: Loader phase failure -> sync_error emitted, sync aborts."""
        events = []
        self._run_sync(["snomed"], events.append, api_ok=True, download_ok=True, loader_ok=False)

        error_events = [e for e in events if e.get("type") == "sync_error"]
        assert error_events, "Expected sync_error on loader failure"
        assert "sync_done" not in {e.get("type") for e in events}

    def test_successful_sync_emits_sync_done(self):
        """Happy path: successful sync emits sync_done, no sync_error."""
        events = []
        self._run_sync(["snomed"], events.append, api_ok=True, download_ok=True, loader_ok=True)

        assert "sync_done" in {e.get("type") for e in events}
        assert not any(e.get("type") == "sync_error" for e in events)


# ---------------------------------------------------------------------------
# VT-16BF8B33: staleness comparison and admin alert
# ---------------------------------------------------------------------------


class TestTrudStalenessCheck:
    """Verify terminology staleness comparison and admin alert.

    AC1: GET /admin/terminology/status returns local_version, trud_date,
         and up_to_date for each package.
    AC2: A package whose local version is behind TRUD has up_to_date: False.
    AC3: An up-to-date package has up_to_date: True.
    """

    def test_snomed_up_to_date_when_dates_match(self):
        """AC3: SNOMED is up to date when local date matches TRUD release name date."""
        from services.api.app.services.trud_sync import _snomed_up_to_date

        release = {"name": "SNOMEDCT2_41.5.0_20260211000001"}
        assert _snomed_up_to_date("2026-02-11", release) is True

    def test_snomed_not_up_to_date_when_dates_differ(self):
        """AC2: SNOMED is stale when local date is behind TRUD release name date."""
        from services.api.app.services.trud_sync import _snomed_up_to_date

        release = {"name": "SNOMEDCT2_41.5.0_20260211000001"}
        assert _snomed_up_to_date("2025-10-01", release) is False

    def test_snomed_not_up_to_date_when_no_local(self):
        """AC2: SNOMED is stale when no local date exists."""
        from services.api.app.services.trud_sync import _snomed_up_to_date

        release = {"name": "SNOMEDCT2_41.5.0_20260211000001"}
        assert _snomed_up_to_date(None, release) is False

    def test_dmd_up_to_date_when_local_matches(self):
        """AC3: dm+d is up to date when local date >= TRUD release date."""
        from services.api.app.services.trud_sync import _dmd_up_to_date

        release = {"releaseDate": "2026-02-01"}
        assert _dmd_up_to_date("2026-02-01", release) is True

    def test_dmd_not_up_to_date_when_local_behind(self):
        """AC2: dm+d is stale when local date is behind TRUD release date."""
        from services.api.app.services.trud_sync import _dmd_up_to_date

        release = {"releaseDate": "2026-02-01"}
        assert _dmd_up_to_date("2025-12-01", release) is False

    def test_generic_up_to_date_when_local_matches(self):
        """AC3: ICD-10/OPCS-4 is up to date when local mtime >= TRUD release date."""
        from services.api.app.services.trud_sync import _generic_up_to_date

        release = {"releaseDate": "2026-01-15"}
        assert _generic_up_to_date("2026-01-15", release) is True

    def test_generic_not_up_to_date_when_local_behind(self):
        """AC2: ICD-10/OPCS-4 is stale when local mtime is behind TRUD release date."""
        from services.api.app.services.trud_sync import _generic_up_to_date

        release = {"releaseDate": "2026-01-15"}
        assert _generic_up_to_date("2025-10-01", release) is False

    def test_package_status_includes_required_fields(self):
        """AC1: _package_status returns local_version, trud_date, up_to_date."""
        from services.api.app.services.trud_sync import _package_status

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp)
            release = {
                "name": "SNOMEDCT2_41.5.0_20260211000001",
                "releaseDate": "2026-02-11",
                "archiveFileSizeBytes": 0,
            }
            status = _package_status("snomed", external, release)

        assert "local_version" in status
        assert "trud_date" in status
        assert "up_to_date" in status
        assert status["trud_date"] == "2026-02-11"

    def test_package_status_no_release_returns_none_dates(self):
        """AC1: When TRUD is unreachable, trud_date and trud_version are None."""
        from services.api.app.services.trud_sync import _package_status

        with tempfile.TemporaryDirectory() as tmp:
            status = _package_status("snomed", Path(tmp), None)

        assert status["trud_date"] is None
        assert status["trud_version"] is None
        assert status["up_to_date"] is False

    def test_snomed_local_date_detected_from_dir(self):
        """AC1: _snomed_local_date reads dated directories correctly."""
        from services.api.app.services.trud_sync import _snomed_local_date, PACKAGES

        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp)
            snomed_dir = external / PACKAGES["snomed"]["dest"]
            dated = snomed_dir / "SnomedCT_UKClinicalRF2_PRODUCTION_20260211T000001Z"
            dated.mkdir(parents=True)

            result = _snomed_local_date(external)

        assert result == "2026-02-11"

    def test_get_status_shape(self):
        """AC1: get_status returns a dict with 'packages' key containing all four packages."""
        from services.api.app.services.trud_sync import get_status, PACKAGES

        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.api.app.services.trud_sync.get_trud_release", return_value=None):
                status = get_status(Path(tmp))

        assert "packages" in status
        for key in PACKAGES:
            assert key in status["packages"]
            pkg = status["packages"][key]
            assert "local_version" in pkg
            assert "up_to_date" in pkg
