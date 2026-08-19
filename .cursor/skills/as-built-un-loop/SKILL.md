---
name: as-built-un-loop
description: Retrospective as-built rewrite of one User Need and its DI/DO/Risk/VT/VAL chain so Atlas matches the product as built. Use when acceptance criteria are false or untestable, or when the user asks to as-built one UN.
disable-model-invocation: true
---

# As-built User Need loop

Do **one User Need** per run. Stop and report.

Read the product ID from the home-repo overlay. Do not hard-code it.

This is as-built documentation. Change Atlas to match the code. Do not
invent features that are not in this checkout.

## Gather

1. Confirm Atlas MCP works (`get_design_control` on a small VAL or the UN).
2. Read the overlay product ID and the local DO-mapping rule.
3. Never write files under a local `design-controls/` store.

## Act (one UN)

1. Fetch the UN. Audit every acceptance criterion against the product.
2. Rewrite or drop false or untestable lines. Keep 2–5 true, testable
   criteria. Plain English. British spelling. ASCII.
3. For each remaining criterion, update the owning Design Input.
4. Confirm links: HAS_DESIGN_INPUT, IMPLEMENTS, MITIGATES (Class B),
   VERIFIES, TESTS, VALIDATES.
5. Ground Design Outputs on repo-prefixed paths that exist. If the DO is
   released (HTTP 409), open a change request.
6. Align VT and VAL with the product. Record runs only after a real pass.
   Playwright VALs use the validation-runs REST API, not MCP, for evidence.

## Verify

- No fake evidence.
- Note remaining gaps in the run report.
- Do not start the next UN until the user asks.
