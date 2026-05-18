# VT Execution Triage Log

Tooling-only document (not under design control). Captures the triage
state of failures and unusual outcomes from the MVP-scope VT
execution loop. Atlas remains the source of truth for VT status; this
file is the working notebook used to drive day-by-day decisions.

## Failures

### VT-9A17E3D7 -- LLM rule generator applies INJECTION_GUARD, conservative fail, and HITL gate

- File: `services/api/tests/test_guidance_rule_generator.py`
- Result: 45 passed, 2 failed.
- Atlas: marked `failed` 2026-04-20 by the runner.
- Verdict: VT scope is met (INJECTION_GUARD / conservative-fail /
  HITL-gate tests all pass). The two failures are **out-of-scope**
  collateral from the same test file:
  1. `TestCodeSnomed::test_terminology_api_failure_returns_none` --
     environmental: requires AWS credentials. The agentic resolver
     code path was added after this test was written and is not
     mocked. **Action:** patch the test fixture to mock the
     agentic-resolve path, or skip when `AWS_*` env vars are unset.
  2. `TestActionFallbackPolicy::test_expand_action_search_terms_adds_non_urgent_variants`
     -- stale assertion. The production code now emits
     organ-specific variants (e.g. "non-urgent referral for
     suspected bladder cancer") rather than the generic
     "non-urgent referral for suspected urological cancer" the test
     was written against. **Action:** rewrite the test assertion to
     match the current variant set, or change the implementation
     contract back to the generic phrasing if the AC requires it.
- Owner (proposed): guidance-rule-generator squad.
- Re-run: after the two tests above are fixed, re-execute via
  `python -m scripts.vt_execution.run_backlog` (the backlog row
  will pick up automatically).

### VT-C3A50386 -- LLM rule generator (second VT against same file)

- File: `services/api/tests/test_guidance_rule_generator.py`
- Result: same 2 failures as VT-9A17E3D7 (out-of-scope collateral).
- See VT-9A17E3D7 entry for action items. When those two tests are
  fixed, VT-C3A50386 will also flip to pass automatically on re-run.

## Wave-2 false-fail incident (2026-04-20)

A path-inference bug in `build_backlog.py` set `test_file_path` to
the source module (e.g. `libs/nlp/sentence_splitter.py`) when the DO
referenced only the module and not its sibling test file. Wave 2
ran 108 such VTs through pytest, which collected zero tests and
returned exit code 5. The runner translated that to `result=fail`
and recorded the failure in Atlas before the bug was caught.

**Mitigation now in place:**
- `run_pytest_vt.py` translates pytest rc=5 to `result=noop` (not
  fail). No further false-fails will be recorded.
- `discover_test_paths.py` rewrites `needs_test_path` rows to point
  at the real `tests/test_<stem>.py` file. 25 of 108 were resolved
  this way and re-ran; 24 of those 25 passed in Atlas, overwriting
  the prior (incorrect) failed status.

**Residual:** 83 VTs still appear `failed` in Atlas with notes
pointing at `<source_module>.py`. These are NOT real failures of the
device; they are tooling artefacts. Each requires either:
  (a) a real test file authored against the source module, OR
  (b) a DO update so the VT's source_reference points at the test,
      not the production module, and re-run with the new path.

The 83 affected VTs are listed in `paper_vts.txt`. They are tagged
`needs_test_path` in the backlog CSV. They are out of the immediate
execution loop until a test file is authored or located.

## Test-path inference oddities

### VT-110D1103

- Inferred path: `libs/prompts/interpretation_v1.py`
  (a prompt module, not a test file).
- Cause: the linked DO references the prompts package alongside
  the actual test file. The path inference picked the wrong sibling.
- Action: backlog row marked `automation_status=manual`,
  `on_disk=false`. The real test file is in
  `services/api/tests/test_guidance_rule_generator.py` (same as
  VT-9A17E3D7). Once the failures above are resolved, link
  VT-110D1103 to the same test file via Atlas DO update.

## Obsolete-source VTs (2026-04-21)

The following VTs reference source modules that do not exist in the
current tree (and never appeared in git). The implementation either
moved, was renamed, or was deferred. Each needs a DO update in Atlas
before it can run. Until then, leave them as `not_executed` in the
backlog and route to the relevant squad.

| VT | Missing source | Likely target |
|----|----|----|
| VT-110D1103 | `libs/prompts/interpretation_v1.py` | re-link to existing interpretation surface |
| VT-A9411132 | `libs/prompts/interpretation_v1.py` | re-link to existing interpretation surface |
| VT-8FA86B8B | `libs/cypher/completeness_report_queries.py` | source removed; verify whether feature is live |
| VT-CE4E3C57 | `libs/pipeline_graph/edges/integration_fetch_edge.py` | source removed; pipeline-graph squad |
| VT-D4AF7CBD | `services/analysis_worker/app/analyzers/episode_consolidator.py` | source removed; episode-engine squad |
| VT-C3250CA6 | `tests/pipeline_graph/test_completeness_subgraph.py` | test never authored; pair with VT-8FA86B8B |

## Unknown-framework VTs (2026-04-21)

27 VTs cannot be auto-routed because the linked DO does not point at
a single test file. They split into three rough buckets that need a
human owner per bucket. Listed in `paper_vts.txt`.

### UI primitives + design-system (jest/playwright)
- VT-A6893653 -- AppShell + ConfirmDialog + StatusDot + TermSearch (a11y)
- VT-3093A2DA -- design tokens
- VT-71391783 -- UI safety / a11y / usability
- VT-1087F4F8 -- useMotion() reduced motion
- VT-D11C0619 -- Phase 6 cleanup (flag, duplicates, fonts, lint)
- VT-2C80866B -- Training Data tab chrome
- VT-CBEF5CBA -- CRUD Knowledge tabs chrome
- VT-CB995607 -- Wave E Phase 1 knowledge primitives
- VT-95AC6642 -- guideline update review surface
- VT-9E3A3E6E -- Pathways admin list (already jest, see CSV)
- VT-E265DA74 -- knowledge base authoring + staging surface
- VT-D32A687B -- operations admin + DQ surface
- VT-0010386B -- reviewer workflow + change-control surface
- Owner: design-system + UI squad

### Backend / pipeline / coding (pytest)
- VT-D9893728 -- Coding Verification Consensus
- VT-88712658 -- Audit Domain and Subdomain Configuration
- VT-51A869C2 -- data-gap disclosure + small-cohort suppression
- VT-51320DA9 -- ServiceDataRequirement registry
- VT-364DA55D -- Loop 2 Surface Form + Two-Reviewer Gate
- VT-B764F925 -- patient shortlisting + recall
- VT-FFF3909C -- NLP training / audit agent / FHIR exposure
- VT-A0FAF859 -- ValueSet + ConceptMap mgmt
- VT-DB062291 -- prompt runtime cache marker / core+dynamic split
- VT-7C4A1B8C -- NER-first extraction routing + pre-filter
- VT-1E5FC70A -- authoritative source monitoring + release mgmt
- VT-0F4D43A7 -- Terminology Service Verification
- VT-C26E6D31 -- Terminology Writeback
- Owner: api / pipeline squad

### Cross-cutting infra (system test)
- VT-7C3FE303 -- Auto-Scaling Worker Architecture
- VT-C23AF9A2 -- Performance and Scaling Verification
- Owner: platform squad

Each VT in this section needs:
1. The Atlas DO updated with `source_reference` pointing at a real
   test file (or a list of files, comma-separated), AND
2. The acceptance_criteria mapped 1:1 to a `it()` / `def test_*`.

Until both are done, the runner will skip them and they will
continue to count against MVP "not executed".

## Integration-heavy script VTs (2026-04-21)

The following VTs target large investigation scripts (>1000 LOC) that
exercise LLMs, Neo4j writes, sqlite checkpoints, and a multi-stage
audit trail. Unit-testing them is low value relative to a small
integration test that drives the script with a mocked LLM and an
ephemeral neo4j-test container. Triaged as `needs_test_path` in the
backlog; route to the audit-loop squad.

- VT-19165B6F -- `scripts/remediate_audit_findings.py`
- VT-D4BFB2F4 -- `scripts/investigations/audit_encounter_coding.py`
