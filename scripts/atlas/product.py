"""Single source of truth for the canonical Atlas product id.

2026-07 CTO peer-review item 4 (product id / config drift): all live
Atlas authoring/consistency tooling must import `PRODUCT_ID` from here
instead of spelling the literal string, so a future product migration
only needs one edit point and CI can assert the value never drifts.

Verified live (2026-07-02) via `get_design_control_stats` on the
`user-atlas-design-controls` MCP server: this product id has 19 User
Needs, 97 Design Inputs, 51 Design Outputs, 116 Verification Tests, 14
Validation Tests, and 50 Risks -- a real, populated Atlas product, not a
placeholder.

The prior id, `PROD-LEO-CORE-AI-20260415-6AE8A23B`, remains valid as a
historical reference inside timestamped audit-trail evidence (see
`compliance/atlas-migration-evidence/**`) and must never be edited there
-- see `.cursor/rules/atlas-design-controls-first.mdc`. It must not be
used as the live/current id anywhere else.
"""

from __future__ import annotations

PRODUCT_ID = "PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4"

# Kept only so tooling/tests can recognise (and reject) the superseded id
# outside historical evidence; never use this as a live/current value.
LEGACY_PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
