# Phase 13a-iv - Atlas trace header convention

The convention below is the spec for the Phase 13c rewriter. Every
Class B+ source file in `libs/` and `services/` must carry a single
trace header that names its owning Atlas Design Output (and, where
relevant, the parent Design Input and any controlled Risks).

This is the only place we are willing to encode design-control IDs
inside source code; any other reference must be deleted or rewritten.

## Why a header (not scattered comments)

- One canonical place per file -- a grep finds the trace in O(1).
- Survives refactors (a moved file moves the header with it).
- Friendly to greppability and to the upcoming `phase13c_*` rewriter.
- Easy to assert in CI later (every Class B+ file must contain
  exactly one `Atlas trace:` block).

## Block format

The block is delimited so it can be machine-located. Inside the
block, every line uses an Atlas dcId (UUID8 form, e.g. `DO-A6D3FE39`),
never a legacy `*-LEO-AI-N` id.

### Python (`.py`)

The block lives at the very top of the module docstring, immediately
after the one-line summary:

```python
"""Cohort analytics helpers.

Atlas trace:
  DO: DO-A6D3FE39  (https://atlas/.../DO-A6D3FE39)
  DI: DI-9F2C1B4E
  Risks: R-72C9B609
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A6D3FE39")
"""
```

If the file has no module docstring today, the rewriter inserts one
whose only content is the Atlas trace block (so we never push code
above it).

### TypeScript / TSX (`.ts`, `.tsx`)

The block lives in a JSDoc comment at the top of the file, before
any imports:

```typescript
/**
 * Cohort analytics helpers.
 *
 * Atlas trace:
 *   DO: DO-A6D3FE39
 *   DI: DI-9F2C1B4E
 *   Risks: R-72C9B609
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A6D3FE39")
 */
```

## Field rules

- `DO:` is REQUIRED. Every Class B+ file has exactly one owning DO.
  Files that resolve to multiple DOs in `phase13a-file-trace-audit.csv`
  get the lexicographically smallest dcId on the `DO:` line; any
  others go on a `Also implements:` line below.
- `DI:` is REQUIRED. The DI is `IMPLEMENTS`-linked to the DO in
  Atlas. If a DO has multiple parent DIs, list them comma-separated
  on a single line.
- `Risks:` is OPTIONAL. Only include risks that are
  `MITIGATES`-linked to one of the DIs above in Atlas.
- `Look up via:` is REQUIRED. It documents the exact MCP tool call
  a future engineer (or AI agent) can paste into Atlas to read the
  authoritative spec. Always cite the `DO:` dcId here, not the DI.
- The block ends with a blank docstring/comment line. No other
  metadata is allowed inside the trace block.

## Forbidden after Phase 13c

- Any reference of the form `(DI|DO|UN|VT|VAL|R)-LEO-AI-\d+` outside
  the migration evidence (`compliance/atlas-migration-evidence/**`)
  and the migration scripts (`scripts/atlas/**`). The rewriter
  strips every such occurrence in code comments and replaces it via
  the legacy-to-Atlas map. Inline-id references (e.g. mid-line text)
  that the rewriter cannot safely strip are flagged for review and
  not touched.
- Multiple `Atlas trace:` blocks in one file.
- A trace block that names a legacy id.
- A trace block where the `DO:` field cannot be resolved to a real
  Atlas dcId via `phase13a-legacy-to-atlas.csv`.

## Files we do NOT add a header to

The rewriter skips:

- Any path under `tests/`, `e2e/`, `services/ui/src/__tests__/`,
  `services/ui/e2e/`, `**/test_*.py`, or `**/*.test.ts(x)` --
  test files trace to a VT, not a DO; the VT id appears in the
  test docstring (different convention, governed by
  `atlas-vt-enforcement.mdc`).
- `__init__.py` files (no executable surface beyond re-exports).
- Auto-generated files (Next.js routes that exist only to
  re-export, declaration-only `.d.ts`, etc.).
- Files under `services/ui/src/lib/types.ts` style "pure type"
  modules: these are flagged for human review rather than auto-headed
  to avoid coupling type-only files to a single DO.

## Resolution algorithm (Phase 13c rewriter)

For each candidate file:

1. Look up `phase13a-file-trace-audit.csv`.
2. If `header_state == "atlas"`, leave the file alone (it already
   has the canonical block) but record it in the audit ledger.
3. If `header_state == "legacy"`, replace every legacy id in the
   file via the legacy-to-Atlas map (where a mapping exists),
   then ensure a trace block exists at the top of the file. If
   any legacy id has no mapping, leave the in-text legacy id but
   prepend a `# TODO(atlas): unmapped legacy id ...` line and add
   the file to the per-run review list.
4. If `header_state == "none"` AND the file resolves to at least
   one Atlas DI/DO via the audit, insert the canonical trace block
   at the top of the file.
5. If `header_state == "none"` AND the file does not resolve, the
   file is added to `phase13c-uncovered.csv` for triage; no header
   is inserted (we will not invent an owning DO).

## Cross-link to Atlas-side fix

In parallel, Phase 13b walks `phase13a-do-source-reference-audit.csv`
and writes the canonical file list onto every Atlas DO via
`update_design_output(source_reference=...)`. So after 13b + 13c,
the trace is bidirectional and keyed on Atlas dcIds:

- File header points to its owning DO (Atlas dcId).
- Atlas DO's `source_reference` lists the file path.
- `IMPLEMENTS` link in Atlas ties the DO back to its DI.

## Why dcIds rather than UUIDs

Atlas exposes both the human-friendly `dcId` (e.g. `DO-A6D3FE39`)
and an internal UUID. The `dcId` is stable, copy/pasteable, and the
exact form `get_design_control(dc_id=...)` accepts. UUIDs are only
needed by `update_*` and `record_*` calls; the rewriter does not
expose them in source.
