"""Shared analytics helpers for LEO-AI-CORE.

This package is the single source of truth for cohort definitions used
by every NCDA analytics endpoint. See DI-LEO-AI-134 and R-LEO-AI-092.

Public API:

* ``CONFIRMED_CANCER_CLAUSE``            Canonical Cypher WHERE fragment
* ``SUSPECTED_CANCER_REFERRAL_CLAUSE``   2WW-route-only variant
* ``confirmed_cancer_where``             Render helper with optional alias
* ``suspected_cancer_referral_where``    Render helper with optional alias
"""

from libs.analytics.cohorts import (
    CONFIRMED_CANCER_CLAUSE,
    SUSPECTED_CANCER_REFERRAL_CLAUSE,
    confirmed_cancer_where,
    suspected_cancer_referral_where,
)

__all__ = [
    "CONFIRMED_CANCER_CLAUSE",
    "SUSPECTED_CANCER_REFERRAL_CLAUSE",
    "confirmed_cancer_where",
    "suspected_cancer_referral_where",
]
