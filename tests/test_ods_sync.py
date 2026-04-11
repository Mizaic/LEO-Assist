"""ODS nightly sync job — automated tests.

Verification protocol: VT-LEO-AI-048
Risk coverage: R-LEO-AI-038 through R-LEO-AI-045

All 12 test cases (TC-001 through TC-012) defined in VT-LEO-AI-048.yaml.

Tests use unittest.mock to patch:
  - httpx.Client (ODS API calls)
  - libs.neo4j_client.client.PatientGraphClient (Neo4j writes)
  - libs.audit.audit_emitter (audit event emission)
  - time.sleep (backoff delay verification)

The implementation lives in:
  - libs/ods/client.py            (OdsOrg, OdsNotFoundError, OdsApiError, OdsRateLimitError)
  - services/ods_sync/app/sync_service.py   (SyncService.run(), SyncService.process_org())
  - services/ods_sync/app/circuit_breaker.py (CircuitBreaker)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build FHIR-style ODS responses
# ---------------------------------------------------------------------------


def _fhir_org(
    ods_code: str = "C84065",
    name: str = "Springfield Medical Centre",
    active: bool = True,
    type_code: str = "RO182",  # GP Practice
) -> dict:
    """Return a minimal FHIR STU3 Organization resource."""
    return {
        "resourceType": "Organization",
        "id": ods_code,
        "name": name,
        "active": active,
        "type": [
            {
                "coding": [
                    {
                        "code": type_code,
                        "system": "https://directory.spineservices.nhs.uk/STU3/CodeSystem/ODSAPI-OrganizationRole-1",
                    }
                ]
            }
        ],
        "address": [
            {"line": ["1 High Street"], "city": "Springfield", "postalCode": "SP1 1AA"}
        ],
    }


def _mock_httpx_get(
    fhir_data: dict | None = None, status_code: int = 200, text: str | None = None
):
    """Return a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    if fhir_data is not None:
        resp.json.return_value = fhir_data
        resp.text = json.dumps(fhir_data)
    elif text is not None:
        resp.json.side_effect = ValueError("Not JSON")
        resp.text = text
    return resp


def _make_neo4j_org(
    org_id: str = "org-001",
    ods_code: str = "C84065",
    name: str = "Springfield Medical Centre",
    org_type: str = "gp",
    ods_sync_status: str | None = None,
) -> dict:
    """Return a dict resembling a row from LIST_ORGS_WITH_ODS_CODE."""
    return {
        "id": org_id,
        "ods_code": ods_code,
        "name": name,
        "labels": ["GPPractice", "Organization"],
        "ods_sync_status": ods_sync_status,
    }


# ---------------------------------------------------------------------------
# TC-001: Name mismatch detected and written
# ---------------------------------------------------------------------------


class TestTC001NameMismatch:
    """VT-LEO-AI-048 TC-001 — Name mismatch detected and written to Neo4j."""

    def test_name_mismatch_sets_status_and_discrepancy(self):
        """ODS returns different name → ods_sync_status='mismatch', discrepancy written."""
        from libs.ods.client import OdsOrg

        leo_org = _make_neo4j_org(name="Springfield Medical Centre")
        ods_org = OdsOrg(
            ods_code="C84065",
            name="Springfield Medical Practice",  # different
            status="Active",
            org_type="gp",
            address={
                "line1": "1 High Street",
                "city": "Springfield",
                "postcode": "SP1 1AA",
            },
        )

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org", return_value=ods_org
            ) as mock_ods,
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            # Find the UPDATE_ORG_ODS_SYNC call
            calls = neo_instance.run.call_args_list
            sync_call = next(
                (
                    c
                    for c in calls
                    if "UPDATE_ORG_ODS_SYNC" in str(c)
                    or (c.args and "ods_sync_status" in str(c.kwargs))
                ),
                None,
            )
            # Verify mismatch status was written (implementation detail: check kwargs)
            write_kwargs = [c.kwargs for c in calls]
            statuses = [kw.get("status") for kw in write_kwargs if "status" in kw]
            discrepancies = [
                kw.get("discrepancy") for kw in write_kwargs if "discrepancy" in kw
            ]

            assert (
                "mismatch" in statuses
            ), f"Expected 'mismatch' in written statuses, got: {statuses}"
            assert any(
                d and isinstance(d, dict) and "name" in d for d in discrepancies
            ), f"Expected name discrepancy in: {discrepancies}"


# ---------------------------------------------------------------------------
# TC-002: Inactive org flagged as closed — closure alert emitted, org not suspended
# ---------------------------------------------------------------------------


class TestTC002InactiveClosed:
    """VT-LEO-AI-048 TC-002 — Inactive ODS status flags org as closed."""

    def test_inactive_org_flags_closed_emits_alert_no_deletion(self):
        """ODS returns Inactive → ods_sync_status='closed'; alert emitted; no DETACH DELETE."""
        from libs.ods.client import OdsOrg

        leo_org = _make_neo4j_org()
        ods_org = OdsOrg(
            ods_code="C84065",
            name="Springfield Medical Centre",
            status="Inactive",
            org_type="gp",
            address={},
        )

        with (
            patch("services.ods_sync.app.sync_service.get_org", return_value=ods_org),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch(
                "services.ods_sync.app.sync_service.emit_ods_closure_alert"
            ) as mock_alert,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            write_kwargs = [c.kwargs for c in neo_instance.run.call_args_list]
            statuses = [kw.get("status") for kw in write_kwargs if "status" in kw]
            assert "closed" in statuses, f"Expected 'closed' in {statuses}"

            mock_alert.assert_called_once()

            # Ensure no DETACH DELETE called
            all_queries = [str(c) for c in neo_instance.run.call_args_list]
            assert not any(
                "DETACH DELETE" in q for q in all_queries
            ), "DETACH DELETE must not be called"


# ---------------------------------------------------------------------------
# TC-003: ODS 404 treated as closed
# ---------------------------------------------------------------------------


class TestTC003NotFoundClosed:
    """VT-LEO-AI-048 TC-003 — ODS 404 treated identically to Inactive."""

    def test_ods_404_flags_closed(self):
        """ODS returns 404 → OdsNotFoundError caught → ods_sync_status='closed'."""
        from libs.ods.client import OdsNotFoundError

        leo_org = _make_neo4j_org()

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=OdsNotFoundError("Not found"),
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch(
                "services.ods_sync.app.sync_service.emit_ods_closure_alert"
            ) as mock_alert,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            write_kwargs = [c.kwargs for c in neo_instance.run.call_args_list]
            statuses = [kw.get("status") for kw in write_kwargs if "status" in kw]
            assert "closed" in statuses
            mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# TC-004: Org type mismatch flagged — type not auto-corrected
# ---------------------------------------------------------------------------


class TestTC004TypeMismatch:
    """VT-LEO-AI-048 TC-004 — Type mismatch flagged; type never auto-corrected."""

    def test_type_mismatch_recorded_no_label_change(self):
        """ODS returns 'pcn' for an org LEO has as 'icb' → discrepancy, no label change."""
        from libs.ods.client import OdsOrg

        leo_org = _make_neo4j_org(org_type="icb")
        leo_org["labels"] = ["ICB", "Organization"]
        ods_org = OdsOrg(
            ods_code="C84065",
            name="Springfield Medical Centre",
            status="Active",
            org_type="pcn",  # DIFFERENT
            address={},
        )

        with (
            patch("services.ods_sync.app.sync_service.get_org", return_value=ods_org),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            write_kwargs = [c.kwargs for c in neo_instance.run.call_args_list]
            discrepancies = [
                kw.get("discrepancy") for kw in write_kwargs if "discrepancy" in kw
            ]
            assert any(
                d and "type" in d for d in discrepancies
            ), "Expected type discrepancy"

            # No SET label changes
            all_queries = [str(c) for c in neo_instance.run.call_args_list]
            assert not any("SET labels" in q or "REMOVE" in q for q in all_queries)


# ---------------------------------------------------------------------------
# TC-005: No write on exact match — only last_checked updated
# ---------------------------------------------------------------------------


class TestTC005NoWriteOnMatch:
    """VT-LEO-AI-048 TC-005 — Exact match: only ods_sync_last_checked updated via batch."""

    def test_exact_match_adds_to_batch_no_individual_write(self):
        """Exact ODS match → org added to batch list; no UPDATE_ORG_ODS_SYNC call."""
        from libs.ods.client import OdsOrg

        leo_org = _make_neo4j_org(name="Springfield Medical Centre")
        ods_org = OdsOrg(
            ods_code="C84065",
            name="Springfield Medical Centre",  # matches
            status="Active",
            org_type="gp",
            address={},
        )

        with (
            patch("services.ods_sync.app.sync_service.get_org", return_value=ods_org),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            # Should add to batch — verify via the SyncService internal batch list
            assert (
                len(svc._batch_no_change) == 1
            ), f"Expected 1 in batch, got: {svc._batch_no_change}"

            # No individual mismatch write
            write_kwargs = [c.kwargs for c in neo_instance.run.call_args_list]
            statuses = [kw.get("status") for kw in write_kwargs if "status" in kw]
            assert "mismatch" not in statuses
            assert "closed" not in statuses


# ---------------------------------------------------------------------------
# TC-006: Circuit breaker aborts after 5 consecutive failures
# ---------------------------------------------------------------------------


class TestTC006CircuitBreaker:
    """VT-LEO-AI-048 TC-006 — Circuit breaker aborts sync after 5 consecutive errors."""

    def test_circuit_breaker_aborts_at_threshold(self):
        """5 consecutive OdsApiError → sync aborts; orgs 6-10 not processed."""
        from libs.ods.client import OdsApiError

        orgs = [
            _make_neo4j_org(org_id=f"org-{i:03d}", ods_code=f"X{i:05d}")
            for i in range(10)
        ]

        call_count = 0

        def ods_side_effect(ods_code, **kwargs):
            nonlocal call_count
            call_count += 1
            raise OdsApiError(f"Connection refused for {ods_code}")

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch(
                "services.ods_sync.app.sync_service.emit_ods_sync_summary"
            ) as mock_summary,
        ):

            neo_instance = MockNeo.return_value
            neo_instance.run.return_value = orgs
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.run()

            assert (
                call_count <= 5
            ), f"Expected ≤5 ODS calls before abort, got {call_count}"
            mock_summary.assert_called_once()
            summary_kwargs = mock_summary.call_args.kwargs
            assert summary_kwargs.get("aborted") is True


# ---------------------------------------------------------------------------
# TC-007: Single per-org failure does not stop rest of sync
# ---------------------------------------------------------------------------


class TestTC007IsolatedFailure:
    """VT-LEO-AI-048 TC-007 — Single OdsApiError does not stop the sync loop."""

    def test_single_error_continues_processing(self):
        """Org 3 raises OdsApiError; orgs 4-10 continue processing."""
        from libs.ods.client import OdsApiError, OdsOrg

        orgs = [
            _make_neo4j_org(org_id=f"org-{i:03d}", ods_code=f"X{i:05d}")
            for i in range(10)
        ]

        def ods_side_effect(ods_code, **kwargs):
            if ods_code == "X00002":  # 0-indexed: org 3 = index 2
                raise OdsApiError("Simulated failure")
            return OdsOrg(
                ods_code=ods_code,
                name="Test Org",
                status="Active",
                org_type="gp",
                address={},
            )

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch("services.ods_sync.app.sync_service.emit_ods_sync_summary"),
        ):

            neo_instance = MockNeo.return_value
            neo_instance.run.return_value = orgs
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.run()

            # 9 orgs should be processed successfully (added to batch or mismatch)
            processed = svc._processed_count
            assert processed >= 9, f"Expected ≥9 processed, got {processed}"


# ---------------------------------------------------------------------------
# TC-008: 429 triggers exponential backoff and retry
# ---------------------------------------------------------------------------


class TestTC008RateLimitBackoff:
    """VT-LEO-AI-048 TC-008 — 429 triggers backoff; second call succeeds."""

    def test_rate_limit_triggers_backoff_and_retry(self):
        """First ODS call raises OdsRateLimitError; after backoff, second call succeeds."""
        from libs.ods.client import OdsOrg, OdsRateLimitError

        leo_org = _make_neo4j_org()
        call_count = 0

        def ods_side_effect(ods_code, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OdsRateLimitError(f"429 for {ods_code}", status_code=429)
            return OdsOrg(
                ods_code=ods_code,
                name="Springfield Medical Centre",
                status="Active",
                org_type="gp",
                address={},
            )

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch("time.sleep") as mock_sleep,
        ):

            neo_instance = MockNeo.return_value
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.process_org(leo_org, run_id="run-001")

            assert (
                call_count == 2
            ), f"Expected 2 ODS calls (1 429 + 1 success), got {call_count}"
            mock_sleep.assert_called()
            sleep_duration = mock_sleep.call_args_list[0].args[0]
            assert sleep_duration >= 1, f"Expected backoff ≥1s, got {sleep_duration}s"


# ---------------------------------------------------------------------------
# TC-009: Orgs without ods_code are skipped
# ---------------------------------------------------------------------------


class TestTC009NoOdsCodeSkipped:
    """VT-LEO-AI-048 TC-009 — Orgs without ods_code are never sent to ODS API."""

    def test_orgs_without_ods_code_not_queried(self):
        """LIST_ORGS_WITH_ODS_CODE excludes orgs with null ods_code by design."""
        # The query itself handles this: WHERE o.odsCode IS NOT NULL AND o.odsCode <> ''
        # We verify by asserting the Cypher constant contains the filter.
        from libs.cypher.admin_queries import LIST_ORGS_WITH_ODS_CODE

        assert "IS NOT NULL" in LIST_ORGS_WITH_ODS_CODE
        assert "odsCode" in LIST_ORGS_WITH_ODS_CODE

    def test_empty_ods_code_not_processed(self):
        """If any org sneaks through with empty ods_code, it is skipped by the service."""
        with (
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch("services.ods_sync.app.sync_service.emit_ods_sync_summary"),
        ):

            neo_instance = MockNeo.return_value
            # Return one org with empty ods_code
            neo_instance.run.return_value = [
                {
                    "id": "org-001",
                    "ods_code": "",
                    "name": "Test",
                    "labels": [],
                    "ods_sync_status": None,
                }
            ]
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)

            with patch("services.ods_sync.app.sync_service.get_org") as mock_ods:
                svc.run()
                mock_ods.assert_not_called()


# ---------------------------------------------------------------------------
# TC-010: Batch summary audit event on completion
# ---------------------------------------------------------------------------


class TestTC010SummaryAudit:
    """VT-LEO-AI-048 TC-010 — emit_ods_sync_summary called with correct counts."""

    def test_summary_emitted_with_correct_counts(self):
        """Run with 6 no-change, 2 mismatch, 1 closed, 1 error → correct summary."""
        from libs.ods.client import OdsApiError, OdsOrg

        def make_org(i, ods_code):
            return {
                "id": f"org-{i}",
                "ods_code": ods_code,
                "name": f"Org {i}",
                "labels": ["GPPractice", "Organization"],
                "ods_sync_status": None,
            }

        orgs = [make_org(i, f"C{i:05d}") for i in range(10)]

        call_idx = 0

        def ods_side_effect(ods_code, **kwargs):
            nonlocal call_idx
            i = call_idx
            call_idx += 1
            if i < 6:
                return OdsOrg(
                    ods_code=ods_code,
                    name=f"Org {i}",
                    status="Active",
                    org_type="gp",
                    address={},
                )
            elif i < 8:
                return OdsOrg(
                    ods_code=ods_code,
                    name=f"DIFFERENT NAME {i}",
                    status="Active",
                    org_type="gp",
                    address={},
                )
            elif i == 8:
                return OdsOrg(
                    ods_code=ods_code,
                    name=f"Org {i}",
                    status="Inactive",
                    org_type="gp",
                    address={},
                )
            else:
                raise OdsApiError("Simulated error")

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch(
                "services.ods_sync.app.sync_service.emit_ods_sync_summary"
            ) as mock_summary,
            patch("services.ods_sync.app.sync_service.emit_ods_closure_alert"),
        ):

            neo_instance = MockNeo.return_value
            neo_instance.run.return_value = orgs
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.run()

            mock_summary.assert_called_once()
            kw = mock_summary.call_args.kwargs
            assert kw.get("checked") == 10, f"Expected checked=10, got {kw}"
            assert kw.get("mismatches") == 2, f"Expected mismatches=2, got {kw}"
            assert kw.get("closures") == 1, f"Expected closures=1, got {kw}"
            assert kw.get("errors") == 1, f"Expected errors=1, got {kw}"


# ---------------------------------------------------------------------------
# TC-011: Malformed ODS response handled gracefully
# ---------------------------------------------------------------------------


class TestTC011MalformedResponse:
    """VT-LEO-AI-048 TC-011 — Non-JSON ODS response → OdsApiError → org marked error."""

    def test_malformed_response_raises_api_error(self):
        """libs.ods.client raises OdsApiError on non-JSON 200 response."""
        import httpx
        from libs.ods.client import OdsApiError as OdsApiErr

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "<html>Service Unavailable</html>"

        with patch("httpx.Client") as MockClient:
            mock_ctx = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_response

            with pytest.raises(OdsApiErr):
                from libs.ods.client import get_org

                get_org("C84065")

    def test_malformed_response_marks_error_continues(self):
        """Sync service catches OdsApiError from malformed response; marks error; continues."""
        from libs.ods.client import OdsApiError, OdsOrg

        orgs = [
            _make_neo4j_org(org_id="org-bad", ods_code="CBAD00"),
            _make_neo4j_org(org_id="org-ok", ods_code="COK001"),
        ]

        call_idx = 0

        def ods_side_effect(ods_code, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if ods_code == "CBAD00":
                raise OdsApiError("Malformed response")
            return OdsOrg(
                ods_code=ods_code,
                name="OK Org",
                status="Active",
                org_type="gp",
                address={},
            )

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch("services.ods_sync.app.sync_service.emit_ods_sync_summary"),
        ):

            neo_instance = MockNeo.return_value
            neo_instance.run.return_value = orgs
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.run()

            assert call_idx == 2, "Both orgs should have been attempted"
            assert svc._error_count == 1, f"Expected 1 error, got {svc._error_count}"


# ---------------------------------------------------------------------------
# TC-012: BATCH_UPDATE_ODS_CHECKED used in batches of ≤500
# ---------------------------------------------------------------------------


class TestTC012BatchWrite:
    """VT-LEO-AI-048 TC-012 — No-change orgs use BATCH_UPDATE_ODS_CHECKED in ≤500 batches."""

    def test_600_no_change_orgs_use_2_batches(self):
        """600 no-change orgs → BATCH_UPDATE_ODS_CHECKED called exactly twice (500 + 100)."""
        from libs.ods.client import OdsOrg

        orgs = [
            {
                "id": f"org-{i:04d}",
                "ods_code": f"C{i:05d}",
                "name": f"Org {i}",
                "labels": ["GPPractice", "Organization"],
                "ods_sync_status": None,
            }
            for i in range(600)
        ]

        def ods_side_effect(ods_code, **kwargs):
            i = int(ods_code[1:])
            return OdsOrg(
                ods_code=ods_code,
                name=f"Org {i}",
                status="Active",
                org_type="gp",
                address={},
            )

        from libs.cypher.admin_queries import BATCH_UPDATE_ODS_CHECKED

        with (
            patch(
                "services.ods_sync.app.sync_service.get_org",
                side_effect=ods_side_effect,
            ),
            patch("services.ods_sync.app.sync_service.PatientGraphClient") as MockNeo,
            patch("services.ods_sync.app.sync_service.emit_ods_sync_summary"),
        ):

            neo_instance = MockNeo.return_value
            neo_instance.run.return_value = orgs
            from services.ods_sync.app.sync_service import SyncService

            svc = SyncService(neo_client=neo_instance)
            svc.run()

            # Count how many times BATCH_UPDATE_ODS_CHECKED query was called
            batch_calls = [
                c
                for c in neo_instance.run.call_args_list
                if c.args and c.args[0] == BATCH_UPDATE_ODS_CHECKED
            ]
            assert (
                len(batch_calls) == 2
            ), f"Expected 2 BATCH_UPDATE_ODS_CHECKED calls (500+100), got {len(batch_calls)}"
            # Verify batch sizes
            batch_sizes = [
                len(c.kwargs.get("orgs", c.args[1] if len(c.args) > 1 else []))
                for c in batch_calls
            ]
            assert 500 in batch_sizes, f"Expected one batch of 500, got {batch_sizes}"
            assert 100 in batch_sizes, f"Expected one batch of 100, got {batch_sizes}"
