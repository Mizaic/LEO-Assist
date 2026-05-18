---
name: atlas-codebase-audit
description: Audits a change, file set, or pull request and produces an implementation evidence map for Atlas design controls. Use when the user asks for a codebase audit, an evidence map, or to identify what design controls (UN, DI, DO, Risk, VT, VAL) are touched by code changes in the LEO Clinical Decision Support repo.
---

# Atlas Codebase Audit

## When to use

- The user asks for a "codebase audit", "evidence map",
  "implementation map", or "what design controls does this touch".
- A pull request or change set needs to be matched to Atlas
  artefacts before `atlas-control-author` writes anything.
- A periodic sweep of the LEO CDS implementation surfaces is due.

This skill is read-only. It never calls Atlas write tools. It
produces an evidence map that the orchestrator
(`atlas-control-author`) feeds into the decision engine.

## What it produces

A single in-memory evidence map shaped like:

```
evidence_map:
  change_kind: <one of decision-engine categories>
  safety_class: <A | B>
  un_clusters: [clinical_facts, clinical_terminology, ...]
  surfaces:
    api_routes: [path:function, ...]
    workers: [path:class, ...]
    ui_components: [path:component, ...]
    prompts: [path, ...]
    cypher_or_neo4j: [path:query, ...]
    interfaces: [topic_or_queue: path, ...]
  tests:
    pytest: [path, ...]
    jest: [path, ...]
    e2e: [path, ...]
  out_of_scope_signals: [reason, ...]
```

## Audit steps

Copy this checklist into the chat and tick items off:

```
Audit progress:
- [ ] Scope the audit (files, PR, or module)
- [ ] Map API surfaces
- [ ] Map worker surfaces
- [ ] Map UI surfaces
- [ ] Map prompts and model calls
- [ ] Map Cypher and Neo4j writes
- [ ] Map interfaces (pubsub, queues, completion events)
- [ ] Locate tests
- [ ] Classify change_kind and safety_class
- [ ] Match to UN clusters
- [ ] Flag out-of-scope signals
- [ ] Emit evidence map
```

### Step 1 - Scope the audit

Ask the user (or infer from the request) which files, PR, or
module to audit. Default to the `git status` diff plus any files
the user has just mentioned.

Use `Glob`, `Grep`, and `Read`. Never use `cat`, `head`, or
`sed`.

### Step 2 - Map API surfaces

Look under `services/api/app/routers/` and any other FastAPI
router locations. For each touched file, list:

- HTTP method and path
- Function name
- Pydantic request/response model(s)

### Step 3 - Map worker surfaces

Look under `services/coding_worker/`, `services/pipeline_worker/`,
`libs/workflow/`, `libs/pipeline_graph/`. For each touched file,
list:

- Class or coroutine name
- Whether it consumes or publishes messages
- Whether it writes to Neo4j

### Step 4 - Map UI surfaces

Look under `services/ui/src/` for React components, hooks, and
pages. List touched components and any page-level changes that
clinicians would see.

### Step 5 - Map prompts and model calls

Look under `libs/llm_client/`, `libs/prompts/`, and any prompt
templates referenced from workers. List prompt files and
mention which model(s) are configured.

### Step 6 - Map Cypher and Neo4j writes

Look under `libs/cypher/`, `libs/pipeline_graph/subgraphs/`. For
every touched file, list the Cypher patterns being read or
written. Pay close attention to `persist.py`-style writebacks.

### Step 7 - Map interfaces

For pubsub or queue changes, look under `libs/message_bus/`,
`services/pipeline_worker/app/services/progress_callback.py`,
`services/coding_worker/app/services/progress_publisher.py`. List:

- Topic / queue name
- Publisher and subscriber paths
- Whether the change adds, renames, or removes a contract

### Step 8 - Locate tests

Find existing tests for the touched code:

- Python: `tests/...` and `services/*/tests/...`
- UI unit: `services/ui/src/__tests__/...`
- UI e2e: `services/ui/e2e/...`

Note files that should have tests but do not.

### Step 9 - Classify change_kind and safety_class

Use the decision engine to pick `change_kind` and
`safety_class`. See `.cursor/skills/atlas-references/decision-engine.md`.
Default to `class_b_feature` and safety class `B` when in doubt.

### Step 10 - Match to UN clusters

Pick from: `clinical_facts`, `clinical_terminology`,
`pathway_match`, `information_completeness`, `clinician_summary`,
`interface`. Multiple clusters may apply.

### Step 11 - Flag out-of-scope signals

Watch for: `dashboard`, `read-aloud`, OCR, document conversion,
thumbnails, FHIR export, autonomous coding. List anything that
suggests scope drift in `out_of_scope_signals` and surface to
the user before drafting controls. See
`.cursor/skills/atlas-references/vocabulary.md`.

### Step 12 - Emit the evidence map

Print the evidence map to chat in the shape at the top of this
file. The orchestrator picks it up from there.

## Output rules

- ASCII only.
- No secrets, tokens, or patient identifiers.
- File paths are repo-relative.
- Do not invent files; if `Glob` returns nothing, say so.

## Related

- Reference: `.cursor/skills/atlas-references/decision-engine.md`
- Reference: `.cursor/skills/atlas-references/vocabulary.md`
- Next skill: `atlas-control-author` consumes this evidence map.
- Rule: `.cursor/rules/atlas-do-implementation-mapping.mdc`
  describes how the evidence map maps onto DOs.
