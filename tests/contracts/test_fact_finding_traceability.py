"""VT-36FDBFAE: fact-finding traceability to implementation.

Atlas trace:
  UN: UN-89E2AE36
  DO: DO-728930A1
  VT: VT-36FDBFAE

Verifies that fact-finding requirements point to the active implementation,
do not claim upload/scanning/conversion behaviour, and have executable tests.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRACTION = ROOT / "libs/pipeline_graph/subgraphs/extraction.py"
EXTRACTOR = ROOT / "libs/pipeline_graph/subgraphs/_extractor.py"
PERSIST = ROOT / "libs/pipeline_graph/subgraphs/persist.py"
FACT_VT_TEST = ROOT / "tests/test_fact_finding_verification_vts.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vt36fdbfae_tc001_fact_finding_implementation_paths_exist() -> None:
    """AC1 -- fact-finding requirements link to active implementation files."""
    for path in (EXTRACTION, EXTRACTOR, PERSIST, FACT_VT_TEST):
        assert path.is_file(), f"missing implementation evidence: {path}"


def test_vt36fdbfae_tc002_no_upload_scan_or_conversion_claims() -> None:
    """AC2 -- fact finding does not claim upload, scanning, or conversion."""
    combined = "\n".join(_read(path).lower() for path in (EXTRACTION, EXTRACTOR))
    banned_claims = {
        "file upload",
        "document conversion",
        "thumbnail",
        "ocr scan",
        "scanning",
    }

    assert not (banned_claims & set(combined.splitlines()))
    for phrase in banned_claims:
        assert phrase not in combined


def test_vt36fdbfae_tc003_test_link_points_to_active_fact_finding_tests() -> None:
    """AC3 -- the VT test link points at active fact-finding tests."""
    test_source = _read(FACT_VT_TEST)

    assert "DO: DO-728930A1" in test_source
    assert "VT-575882D6" in test_source
    assert "VT-1A36E7D0" in test_source
