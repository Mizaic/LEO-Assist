"""Optional live terminology resolution checks for NG12 EXT fixtures."""

from __future__ import annotations

import os

import pytest

from libs.terminology.client import TerminologyClient

from tests.helpers.ng12_scenario_loader import load_paired_scenarios


def _unique_lookup_terms() -> list[str]:
    _, ext, _ = load_paired_scenarios()
    terms: set[str] = set()
    for row in ext["scenarios"]:
        for t in row.get("llm_response_terms") or []:
            raw = str(t.get("lookup_term") or "").strip()
            if raw:
                terms.add(raw)
    return sorted(terms, key=str.lower)


def _terminology_api_reachable(base_url: str) -> bool:
    try:
        import httpx

        httpx.get(base_url, timeout=2.0)
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not os.getenv("TERMINOLOGY_API_URL", "").strip(),
    reason="TERMINOLOGY_API_URL unset -- skip live terminology check",
)
def test_resolve_all_fixture_lookup_terms_live() -> None:
    """Resolve every unique EXT lookup_term when terminology API URL is set."""
    terms = _unique_lookup_terms()
    assert terms
    base = os.environ["TERMINOLOGY_API_URL"].strip()
    if not _terminology_api_reachable(base):
        pytest.skip("terminology API not reachable -- skip live resolve")
    client = TerminologyClient(base_url=base, timeout=30.0, max_retries=1)
    batch = 30
    for i in range(0, len(terms), batch):
        chunk = terms[i : i + batch]
        resolved = client.resolve(chunk)
        assert resolved, f"empty resolve batch starting at {i}"
