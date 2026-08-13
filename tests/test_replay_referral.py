"""Regression tests for scripts/replay_referral.py's review-bundle helpers.

Found during the six-site pilot review (GY22, LGI5): the runtime DOCUMENTS
write path only sets `assertion` inside the JSON-encoded `context` relationship
property, not as a top-level `r.assertion` property. The first version of
`_chunk_documents` read `r.assertion` directly, so every entity in every
review bundle silently showed `assertion: null` -- defeating the purpose of
reviewing assertion accuracy.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.replay_referral import _resolve_assertion  # noqa: E402


def test_resolve_assertion_reads_context_json_over_top_level_property():
    row = {
        "assertion_prop": None,
        "context_json": '{"assertion": "possible", "negated": false, "uncertain": true}',
    }
    assert _resolve_assertion(row) == "possible"


def test_resolve_assertion_falls_back_to_top_level_property():
    row = {"assertion_prop": "historical", "context_json": None}
    assert _resolve_assertion(row) == "historical"


def test_resolve_assertion_handles_malformed_context_json():
    row = {"assertion_prop": "present", "context_json": "not-json"}
    assert _resolve_assertion(row) == "present"


def test_resolve_assertion_returns_none_when_nothing_available():
    row = {"assertion_prop": None, "context_json": None}
    assert _resolve_assertion(row) is None
