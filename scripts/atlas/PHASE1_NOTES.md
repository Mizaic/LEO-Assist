# Phase 1 Notes (2026-04-19)

## Outcome

109 DI rows from `phase3-di-merge-gap.md` processed.

| Result | Count |
|---|---|
| `updated` (AC merge applied) | 103 |
| `noop` (Atlas already had everything) | 6 |
| Errors | 0 |

Total AC additions across all 103 DIs: 652. No rationale, description, or safety_class fields were modified (Atlas already had every field populated; we are conservative and never overwrite Atlas).

Spot-check: `DI-143F69EB` went from 4 AC (Atlas-original) to 7 AC (4 Atlas + 3 local), updated_at refreshed, all other fields preserved.

## Bugs found and fixed during execution

### Bug 1 -- MCP transport silently swallows tool errors

`fire_atlas_fmea.py`'s `_call_tool` checks for `"error" in resp` (the JSON-RPC envelope error), but the Atlas MCP server returns API errors as `result.content[0].text` starting with `"Error executing tool"`. The original transport parsed this as a successful response and returned `{"_text": "Error executing tool ..."}`. The Phase 1 script treated any non-exception response as success.

**Fix**: `scripts/atlas/_mcp_transport.py` `call_tool()` now raises `McpError` when a text content item starts with `"Error executing tool"`.

### Bug 2 -- update_design_input requires UUID, not dc_id

The schema example says `e.g. DI-ATLAS-042` but in practice the Atlas backend rejects `dc_id: "DI-143F69EB"` with `"Resource not found"` (URL was `.../design-inputs/DI-143F69EB`). The UUID form (e.g. `143f69eb-c5a1-4376-aea1-b7a31fb4c8e7`) works.

**Fix**: `scripts/atlas/phase1_di_merge.py` now passes the UUID from `designInput.id` instead of the `dc_id`. Worth checking whether other `update_*` tools have the same requirement before using them in Phases 2-5.

## Recovery

A test AC ("PHASE1-PROBE: ...") was briefly added to DI-143F69EB during the bug-fix verification and immediately rolled back via a second `update_design_input` call with the original 4 AC. Verified via `get_design_control` that the DI returned to its pre-probe state before the live re-run started.

## Performance

- ~14 sec per pair for the dry-run (dominated by `get_design_control` returning the full traceability tree, ~120 KB per response).
- ~14 sec per pair for the live run as well (still dominated by `get_design_control`; `update_design_input` adds ~0.5 sec).
- 109 pairs took ~24 minutes per run.

## Outputs

- `design-controls/phase7-di-merge-execution.csv` -- per-DI ledger
- `design-controls/phase7-di-merge-execution.md` -- human-readable summary
- `scripts/atlas/.phase1_di_merge_state.json` -- resume-safe state
- `scripts/atlas/.phase1_dry_run.log`, `.phase1_live_run.log`, `.phase1_live_run_v2.log` -- run logs
