"""Simple threshold-based circuit breaker for the ODS nightly sync job.

The circuit breaker counts *consecutive* failures against the ODS API.
When the threshold is reached it raises CircuitOpenError so the sync
job can abort cleanly and emit an alert rather than continuing to
hammer an unavailable API.

The counter resets to zero on any successful ODS call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker threshold is exceeded."""


class CircuitBreaker:
    """Consecutive-failure circuit breaker.

    Args:
        threshold: Number of consecutive failures before the circuit opens.
                   Default: 5 (as per R-LEO-AI-038 mitigation design).
    """

    def __init__(self, threshold: int = 5) -> None:
        self._threshold = threshold
        self._consecutive_failures = 0

    @property
    def is_open(self) -> bool:
        return self._consecutive_failures >= self._threshold

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def record_success(self) -> None:
        """Record a successful call; reset consecutive failure count."""
        if self._consecutive_failures > 0:
            logger.debug(
                "[CircuitBreaker] Success — resetting failure count from %d",
                self._consecutive_failures,
            )
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failure; raise CircuitOpenError if threshold reached."""
        self._consecutive_failures += 1
        logger.warning(
            "[CircuitBreaker] Failure %d / %d",
            self._consecutive_failures,
            self._threshold,
        )
        if self.is_open:
            raise CircuitOpenError(
                f"Circuit breaker opened after {self._consecutive_failures} "
                f"consecutive ODS API failures"
            )
