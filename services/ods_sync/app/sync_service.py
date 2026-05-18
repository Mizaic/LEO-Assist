"""ODS nightly sync service.

Atlas trace:
  DO: DO-31410049
  DI: DI-F46494AE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-31410049")

Core orchestration logic for the LEO ODS Nightly Sync Job.
Designed to run as an Azure Container Apps Job (cron: 0 2 * * *).

For each Organisation node in Neo4j with an ODS code:
  1. Call NHS ODS FHIR API to retrieve current details
  2. Compare name, status, and type with LEO's record
  3. Write sync results atomically to Neo4j
  4. Batch no-change updates via UNWIND for performance
  5. Emit closure alerts for Inactive/404 organisations
  6. Abort on circuit breaker threshold (5 consecutive failures)
  7. Emit a run summary AuditEvent on completion

Risk coverage: R-LEO-AI-038 through R-LEO-AI-045
Verification: VT-LEO-AI-048 tests/test_ods_sync.py
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from libs.audit.audit_emitter import emit_ods_closure_alert, emit_ods_sync_summary
from libs.cypher.admin_queries import (
    BATCH_UPDATE_ODS_CHECKED,
    LIST_ORGS_WITH_ODS_CODE,
    RELABEL_ORG_AS_ALLIANCE,
    RELABEL_ORG_AS_GP,
    RELABEL_ORG_AS_ICB,
    RELABEL_ORG_AS_PCN,
    UPDATE_ORG_ODS_SYNC,
)
from libs.neo4j_client.client import PatientGraphClient
from libs.ods.client import (
    OdsAccessError,
    OdsApiError,
    OdsNotFoundError,
    OdsOrg,
    OdsRateLimitError,
    get_org,
)
from services.ods_sync.app.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Environment configuration
_MAX_RETRIES = int(os.environ.get("ODS_SYNC_MAX_RETRIES", "3"))
_DELAY_MS = int(os.environ.get("ODS_SYNC_DELAY_MS", "1000"))
_CIRCUIT_THRESHOLD = int(os.environ.get("ODS_SYNC_CIRCUIT_THRESHOLD", "5"))
_BATCH_SIZE = int(os.environ.get("ODS_SYNC_BATCH_SIZE", "500"))
_CONCURRENCY = max(1, int(os.environ.get("ODS_SYNC_CONCURRENCY", "8")))

# Maps LEO org label → type string (for discrepancy comparison)
_LABEL_TO_TYPE: dict[str, str] = {
    "GPPractice": "gp",
    "PCN": "pcn",
    "ICB": "icb",
    "CancerAlliance": "alliance",
}

# Maps ODS-confirmed type → the Cypher query that applies the correct Neo4j label.
# Only populated for types where ODS is unambiguously authoritative.
_RELABEL_QUERY: dict[str, str] = {
    "gp": RELABEL_ORG_AS_GP,
    "icb": RELABEL_ORG_AS_ICB,
    "alliance": RELABEL_ORG_AS_ALLIANCE,
    "pcn": RELABEL_ORG_AS_PCN,
}


def _to_json(value: dict | None) -> str | None:
    """Serialise a dict to a JSON string for Neo4j property storage.

    Neo4j properties must be primitive types or arrays; maps are not supported.
    Returns None if value is None or empty.
    """
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def _leo_type_from_labels(labels: list[str]) -> str:
    for label in labels:
        if label in _LABEL_TO_TYPE:
            return _LABEL_TO_TYPE[label]
    return "organization"


class SyncService:
    """Orchestrates the ODS nightly sync for all organisations with ODS codes.

    Attributes exposed for test verification:
        _batch_no_change: list of orgs with no ODS changes (pending batch write)
        _processed_count: total orgs where processing completed without circuit abort
        _mismatch_count: orgs flagged as mismatch
        _closure_count: orgs flagged as closed
        _error_count: orgs where an unexpected error occurred
    """

    def __init__(
        self,
        neo_client: PatientGraphClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._neo = neo_client or PatientGraphClient()
        self._cb = circuit_breaker or CircuitBreaker(threshold=_CIRCUIT_THRESHOLD)
        self._run_id: str = ""
        self._batch_no_change: list[dict[str, Any]] = []
        self._processed_count: int = 0
        self._mismatch_count: int = 0
        self._closure_count: int = 0
        self._error_count: int = 0
        self._relabel_count: int = 0
        # Protects the counters, batch buffer and circuit breaker when
        # process_org is called from multiple worker threads.
        self._state_lock = threading.Lock()

    def run(self) -> None:
        """Run the full ODS sync cycle.

        Loads all orgs with ODS codes from Neo4j, processes each one,
        flushes the no-change batch, then emits a summary audit event.
        """
        self._run_id = str(uuid.uuid4())
        logger.info("[ODS Sync] Starting run %s", self._run_id)

        # Load org list
        orgs = self._neo.run(LIST_ORGS_WITH_ODS_CODE)
        logger.info("[ODS Sync] %d organisations to check", len(orgs))

        aborted = False
        eligible = [o for o in orgs if o.get("ods_code")]

        # Run ODS lookups in parallel. Each call is a remote HTTP request
        # bounded by ODS_SYNC_CONCURRENCY (default 8). The shared counters
        # and circuit breaker are protected by self._state_lock; Neo4j
        # writes go through a thread-safe driver pool.
        def _worker(org: dict[str, Any]) -> bool:
            """Return True on success, False on circuit breaker open."""
            try:
                self.process_org(org, run_id=self._run_id)
                with self._state_lock:
                    self._processed_count += 1
                return True
            except CircuitOpenError:
                return False

        with ThreadPoolExecutor(max_workers=_CONCURRENCY) as pool:
            futures = [pool.submit(_worker, o) for o in eligible]
            for fut in as_completed(futures):
                if not fut.result():
                    logger.error(
                        "[ODS Sync] Circuit breaker opened -- aborting run"
                    )
                    aborted = True
                    for pending in futures:
                        pending.cancel()
                    break

        # Flush no-change batch
        if self._batch_no_change:
            self._flush_batch()

        # Emit summary audit event
        emit_ods_sync_summary(
            run_id=self._run_id,
            checked=self._processed_count,
            mismatches=self._mismatch_count,
            closures=self._closure_count,
            errors=self._error_count,
            aborted=aborted,
        )
        logger.info(
            "[ODS Sync] Run %s complete: processed=%d relabelled=%d mismatches=%d closures=%d errors=%d aborted=%s",
            self._run_id,
            self._processed_count,
            self._relabel_count,
            self._mismatch_count,
            self._closure_count,
            self._error_count,
            aborted,
        )

    def process_org(self, leo_org: dict[str, Any], run_id: str) -> None:
        """Process a single organisation against the ODS API.

        Handles retries for 429 responses, per-org error isolation,
        and circuit breaker failure recording.

        Args:
            leo_org: Row from LIST_ORGS_WITH_ODS_CODE
            run_id: Unique identifier for the current sync run
        """
        org_id: str = leo_org["id"]
        ods_code: str = leo_org["ods_code"]
        leo_name: str = leo_org.get("name", "")
        leo_type: str = _leo_type_from_labels(leo_org.get("labels") or [])

        try:
            ods_org = self._fetch_with_retry(ods_code)
            with self._state_lock:
                self._cb.record_success()
        except OdsNotFoundError:
            with self._state_lock:
                self._cb.record_success()  # 404 is a valid (non-connection) response
            self._flag_closed(
                org_id=org_id,
                org_name=leo_name,
                ods_code=ods_code,
                run_id=run_id,
                ods_parent_ods_code=None,
                ods_address=None,
            )
            with self._state_lock:
                self._closure_count += 1
            return
        except OdsAccessError as exc:
            with self._state_lock:
                self._cb.record_success()
            logger.info("[ODS Sync] Skipping restricted org %s: %s", ods_code, exc)
            return
        except OdsRateLimitError as exc:
            logger.warning("[ODS Sync] Rate limit exhausted for %s: %s", ods_code, exc)
            self._write_error(org_id=org_id, run_id=run_id, error=str(exc))
            with self._state_lock:
                self._error_count += 1
            return
        except OdsApiError as exc:
            logger.warning("[ODS Sync] ODS API error for %s: %s", ods_code, exc)
            self._write_error(org_id=org_id, run_id=run_id, error=str(exc))
            with self._state_lock:
                self._error_count += 1
                self._cb.record_failure()  # connection-level failure -> CB
            return

        # Compare ODS data to LEO record
        discrepancy: dict[str, Any] = {}

        if ods_org.status == "Inactive":
            self._flag_closed(
                org_id=org_id,
                org_name=leo_name,
                ods_code=ods_code,
                run_id=run_id,
                ods_parent_ods_code=ods_org.part_of_ods,
                ods_address=ods_org.address,
            )
            with self._state_lock:
                self._closure_count += 1
            return

        # ODS stores names in UPPERCASE; compare case-insensitively to avoid spurious mismatches
        if ods_org.name and ods_org.name.upper() != leo_name.upper():
            discrepancy["name"] = {"ods": ods_org.name, "leo": leo_name}

        # Type check — mismatch is recorded for review; do not auto-relabel.
        if ods_org.org_type != "unknown" and ods_org.org_type != leo_type:
            discrepancy["type"] = {"ods": ods_org.org_type, "leo": leo_type}

        # Hierarchy check: does ODS parent match what we have in Neo4j?
        current_parent_ods = leo_org.get("current_parent_ods_code")
        if (
            ods_org.part_of_ods
            and current_parent_ods
            and ods_org.part_of_ods.upper() != current_parent_ods.upper()
        ):
            discrepancy["parent_ods_code"] = {
                "ods": ods_org.part_of_ods,
                "leo": current_parent_ods,
            }

        if discrepancy:
            self._write_mismatch(
                org_id=org_id,
                run_id=run_id,
                discrepancy=discrepancy,
                ods_parent_ods_code=ods_org.part_of_ods,
                ods_address=ods_org.address,
            )
            with self._state_lock:
                self._mismatch_count += 1
        else:
            should_flush = False
            with self._state_lock:
                self._batch_no_change.append(
                    {
                        "id": org_id,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id,
                        "ods_parent_ods_code": ods_org.part_of_ods,
                        "ods_address": _to_json(ods_org.address),
                    }
                )
                should_flush = len(self._batch_no_change) >= _BATCH_SIZE
            if should_flush:
                self._flush_batch()

    def _fetch_with_retry(self, ods_code: str) -> OdsOrg:
        """Fetch ODS org with exponential backoff on 429 (R-LEO-AI-039 mitigation)."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return get_org(ods_code)
            except OdsRateLimitError as exc:
                last_exc = exc
                delay_s = (_DELAY_MS / 1000.0) * (2**attempt)
                logger.warning(
                    "[ODS Sync] 429 for %s (attempt %d/%d), backoff %.1fs",
                    ods_code,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay_s,
                )
                time.sleep(delay_s)
        raise last_exc  # type: ignore[misc]

    def _flag_closed(
        self,
        *,
        org_id: str,
        org_name: str,
        ods_code: str,
        run_id: str,
        ods_parent_ods_code: str | None = None,
        ods_address: dict | None = None,
    ) -> None:
        """Write ods_sync_status='closed' and emit a closure alert.

        This is informational ONLY — the org is not suspended or deleted (R-LEO-AI-040).
        """
        self._neo.run(
            UPDATE_ORG_ODS_SYNC,
            org_id=org_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            status="closed",
            discrepancy=None,
            run_id=run_id,
            ods_parent_ods_code=ods_parent_ods_code,
            ods_address=_to_json(ods_address),
        )
        emit_ods_closure_alert(
            org_id=org_id,
            org_name=org_name,
            ods_code=ods_code,
            run_id=run_id,
        )
        logger.warning(
            "[ODS Sync] Closure flagged: org_id=%s ods_code=%s", org_id, ods_code
        )

    def _write_mismatch(
        self,
        *,
        org_id: str,
        run_id: str,
        discrepancy: dict,
        ods_parent_ods_code: str | None = None,
        ods_address: dict | None = None,
    ) -> None:
        """Write ods_sync_status='mismatch' with field-level discrepancy details."""
        self._neo.run(
            UPDATE_ORG_ODS_SYNC,
            org_id=org_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            status="mismatch",
            discrepancy=discrepancy,
            run_id=run_id,
            ods_parent_ods_code=ods_parent_ods_code,
            ods_address=_to_json(ods_address),
        )
        logger.info(
            "[ODS Sync] Mismatch: org_id=%s discrepancy=%s", org_id, discrepancy
        )

    def _write_error(self, *, org_id: str, run_id: str, error: str) -> None:
        """Write ods_sync_status='error' for an org that could not be checked."""
        self._neo.run(
            UPDATE_ORG_ODS_SYNC,
            org_id=org_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            status="error",
            discrepancy=_to_json({"error": error}),
            run_id=run_id,
            ods_parent_ods_code=None,
            ods_address=None,
        )

    def _flush_batch(self) -> None:
        """Flush the no-change batch using UNWIND Cypher for efficiency (R-LEO-AI-045)."""
        # Move pending rows out from under the lock so Neo4j writes do
        # not block other workers adding to the batch.
        with self._state_lock:
            if not self._batch_no_change:
                return
            pending = self._batch_no_change
            self._batch_no_change = []
        for i in range(0, len(pending), _BATCH_SIZE):
            chunk = pending[i : i + _BATCH_SIZE]
            self._neo.run(BATCH_UPDATE_ODS_CHECKED, orgs=chunk)
            logger.debug("[ODS Sync] Flushed %d no-change orgs to Neo4j", len(chunk))
