"""Canonical Atlas product id assertion (2026-07 CTO peer-review item 4:
product id / config drift).

Verified live (2026-07-02) via `get_design_control_stats` on the
`user-atlas-design-controls` MCP server that `PRODUCT_ID` below is a real,
populated Atlas product (19 User Needs, 97 Design Inputs, 51 Design
Outputs, 116 Verification Tests, 14 Validation Tests, 50 Risks) -- not a
placeholder -- before making CI depend on it.

Two things are asserted here:

1. `scripts/atlas/product.py` still spells the agreed canonical id -- this
   catches an accidental edit to the single source-of-truth constant.
2. The superseded id (`LEGACY_PRODUCT_ID`,
   `PROD-LEO-CORE-AI-20260415-6AE8A23B`) does not leak into any
   live/authoring file as if it were still current. Per
   `.cursor/rules/atlas-design-controls-first.mdc`, historical audit-trail
   evidence under `compliance/atlas-migration-evidence/**` (and the
   retired scripts under `scripts/archive/**`) is immutable and must
   never be "fixed" to match the new id -- those two path prefixes are
   excluded from the failure condition. A small, explicit allow-list
   covers the handful of other legitimate historical mentions (completed
   migration-phase notes, point-in-time snapshot descriptions, and cached
   Atlas API responses) found during the 2026-07 sweep; anything outside
   that allow-list is either a live doc that must use the canonical id or
   a new file that needs its own allow-list entry with justification.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.atlas.product import LEGACY_PRODUCT_ID, PRODUCT_ID

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_ID = "PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4"

# Directory prefixes that are entirely exempt: historical audit-trail
# evidence (must never be edited to match a new id) and retired ad-hoc
# scripts (not maintained, not part of any live workflow).
_ALLOWED_PATH_PREFIXES = (
    "compliance/atlas-migration-evidence/",
    "scripts/archive/",
)

# Individual files with a legitimate, reviewed reason to still contain the
# superseded id -- see the 2026-07 product-id sweep. Each entry's reason
# is recorded in the comment beside it so a future edit can re-justify or
# remove the allowance rather than silently keep it.
_ALLOWED_EXACT_FILES = {
    # The single source-of-truth constant: LEGACY_PRODUCT_ID exists
    # specifically to name the superseded id for recognition/rejection.
    "scripts/atlas/product.py",
    # Docstring explicitly marks this as "historical product id
    # reference" -- describes the id a pre-fetched snapshot file was
    # captured under, not a live Atlas call.
    "scripts/atlas_consistency/audit_uns_for_dr1.py",
    # Cached Atlas API response / snapshot data captured under the prior
    # id; not re-fetched live on every run.
    "scripts/atlas/.phase2_atlas_full_cache.json",
    "scripts/atlas_consistency/all_leo_uns_full.json",
    "scripts/atlas_consistency/dr1_attach_v2.json",
    # Completed migration-phase notes (each headed "Status: COMPLETE"):
    # point-in-time records of what those phases actually referenced:
    # rewriting them would falsify the record of what was done.
    "scripts/atlas/PHASE3_NOTES.md",
    "scripts/atlas/PHASE6_NOTES.md",
    "scripts/atlas/PHASE9_NOTES.md",
    "scripts/atlas/PHASE10_NOTES.md",
    "scripts/atlas/PHASE12_NOTES.md",
    # Point-in-time snapshot description ("Snapshot at 2026-04-20"),
    # naming the id that snapshot was captured under.
    "compliance/coverage-waivers.md",
    # Version-history changelog entry describing v1.0.0's original
    # 2026-04-24 issue -- a dated changelog row, not current metadata.
    "compliance/policy/DC-MTP-001-model-training-platform.md",
    # This file itself: it necessarily spells out the superseded id (in
    # its docstring and the allow-list values above) to check for it.
    "tests/test_product_id_canonical.py",
}


def _tracked_and_untracked_files() -> list[str]:
    """All files git considers part of the repo (tracked + untracked,
    but not ignored), so generated/venv/node_modules noise is skipped
    without needing our own exclude list."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _is_allowed(rel_path: str) -> bool:
    if rel_path in _ALLOWED_EXACT_FILES:
        return True
    return any(rel_path.startswith(prefix) for prefix in _ALLOWED_PATH_PREFIXES)


def test_product_id_constant_matches_canonical():
    assert PRODUCT_ID == CANONICAL_ID


def test_legacy_constant_is_the_superseded_id_and_distinct():
    assert LEGACY_PRODUCT_ID == "PROD-LEO-CORE-AI-20260415-6AE8A23B"
    assert LEGACY_PRODUCT_ID != PRODUCT_ID


def test_no_legacy_product_id_outside_allowlist():
    offenders: list[str] = []
    for rel_path in _tracked_and_untracked_files():
        if _is_allowed(rel_path):
            continue
        path = ROOT / rel_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if LEGACY_PRODUCT_ID in text:
            offenders.append(rel_path)

    assert not offenders, (
        "Found the superseded product id "
        f"({LEGACY_PRODUCT_ID!r}) referenced as if current outside the "
        "historical-evidence/archive allow-list. Either update the file "
        "to the canonical id (or an import of PRODUCT_ID), or -- if this "
        "is a genuine new historical record -- add it to "
        f"_ALLOWED_EXACT_FILES in {__file__} with a reason: {offenders}"
    )


def test_allowlisted_files_still_exist():
    """Catches allow-list rot: if one of these files is renamed/deleted,
    the allow-list entry should be cleaned up rather than left dangling."""
    missing = [f for f in _ALLOWED_EXACT_FILES if not (ROOT / f).is_file()]
    assert not missing, f"Allow-listed files no longer exist: {missing}"
