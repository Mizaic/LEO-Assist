"""VT-2487F804: 2026_backfill_review_verdict migration parity.

Hermetic test for ``scripts/migrations/2026_backfill_review_verdict.py``.
No Neo4j required; the migration's single collaborator is an object
with a ``.run(query, **params) -> list[dict]`` method, so we inject
a fake client and assert on the Cypher the script would run.

Pins:

* dry-run never issues a write query,
* direct-map statuses (closed_benign, completed, ...) are backfilled
  without an audit_notes entry,
* inferred statuses (stale_*, closed_related, None) are backfilled
  and their audit_notes line is appended,
* the scan query finds zero rows on a second run because every
  written row has review_verdict set,
* return code is 0 on both dry-run and commit.

Atlas trace:
  DI: DI-E2498DF6
  DO: DO-2A124BA0
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from unittest.mock import patch

from libs.episodes.lifecycle import ReviewVerdict

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "migrations"
    / "2026_backfill_review_verdict.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_backfill_review_verdict", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class _FakeClient:
    """Minimal stand-in for PatientGraphClient.run."""

    def __init__(self, scan_rows: list[dict]) -> None:
        self._scan_rows = scan_rows
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if "RETURN status AS status" in query:
            return list(self._scan_rows)
        # Write queries return the number of rows that matched.
        total = sum(
            int(row.get("n") or 0)
            for row in self._scan_rows
            if str(row.get("status") or "__null__") == params.get("status")
        )
        return [{"n": total}]


def _run_with_client(client: _FakeClient, argv: list[str]) -> int:
    mod = _load_module()
    with patch.object(mod, "PatientGraphClient", lambda: client):
        with patch.object(
            logging.getLogger("backfill_review_verdict"), "info", lambda *a, **k: None
        ):
            with patch("sys.argv", ["prog", *argv]):
                return mod.main()


def test_dry_run_emits_no_write_queries(caplog) -> None:
    client = _FakeClient(
        [
            {"status": "closed_benign", "n": 3},
            {"status": "completed", "n": 2},
        ]
    )
    rc = _run_with_client(client, [])
    assert rc == 0
    writes = [
        q for q, _ in client.calls
        if "SET ep.review_verdict" in q
    ]
    assert writes == []


def test_commit_writes_direct_for_known_status_without_audit_line() -> None:
    client = _FakeClient([{"status": "closed_benign", "n": 3}])
    rc = _run_with_client(client, ["--commit"])
    assert rc == 0
    write_calls = [
        (q, p) for q, p in client.calls if "SET ep.review_verdict" in q
    ]
    assert len(write_calls) == 1
    query, params = write_calls[0]
    assert params["verdict"] == ReviewVerdict.CONFIRMED_BENIGN.value
    assert params["status"] == "closed_benign"
    assert "audit_notes" not in query  # direct path, no audit append


def test_commit_writes_inferred_with_audit_line_for_stale_status() -> None:
    client = _FakeClient([{"status": "stale_no_diagnosis", "n": 1}])
    rc = _run_with_client(client, ["--commit"])
    assert rc == 0
    write_calls = [
        (q, p) for q, p in client.calls if "SET ep.review_verdict" in q
    ]
    assert len(write_calls) == 1
    query, params = write_calls[0]
    # stale_* collapses to completed per verdict_from_legacy_status
    assert params["verdict"] == ReviewVerdict.CONFIRMED_COMPLETED.value
    assert "audit_notes" in query
    assert "stale_no_diagnosis" in params["audit_suffix"]


def test_commit_writes_inferred_audit_line_for_null_status() -> None:
    client = _FakeClient([{"status": None, "n": 2}])
    rc = _run_with_client(client, ["--commit"])
    assert rc == 0
    write_calls = [
        (q, p) for q, p in client.calls if "SET ep.review_verdict" in q
    ]
    assert len(write_calls) == 1
    _, params = write_calls[0]
    assert params["verdict"] == ReviewVerdict.CONFIRMED_ACTIVE.value
    assert "null" in params["audit_suffix"]


def test_idempotent_second_run_finds_nothing_to_do() -> None:
    client = _FakeClient([])
    rc = _run_with_client(client, ["--commit"])
    assert rc == 0
    # Only the scan query ran; no writes.
    assert len(client.calls) == 1
    scan_q, _ = client.calls[0]
    assert "RETURN status AS status" in scan_q


def test_each_known_status_projects_to_expected_verdict() -> None:
    cases = [
        ("closed_benign", ReviewVerdict.CONFIRMED_BENIGN.value),
        ("completed", ReviewVerdict.CONFIRMED_COMPLETED.value),
        ("closed", ReviewVerdict.CONFIRMED_COMPLETED.value),
        ("active", ReviewVerdict.CONFIRMED_ACTIVE.value),
        ("review", ReviewVerdict.CONFIRMED_ACTIVE.value),
        ("merged", ReviewVerdict.CONFIRMED_MERGED.value),
        ("excluded", ReviewVerdict.REJECTED.value),
    ]
    for status, expected in cases:
        client = _FakeClient([{"status": status, "n": 1}])
        _run_with_client(client, ["--commit"])
        writes = [p for q, p in client.calls if "SET ep.review_verdict" in q]
        assert writes and writes[0]["verdict"] == expected, status
