# SBAR Golden Set (VT-LEO-AI-189 TC-009)

Manually-curated regression fixtures for the SBAR generation workflow.
TC-009 is the gate for rolling out any change to:

- `libs/prompts/sbar_situation_v1.py`
- `libs/prompts/sbar_background_v1.py`
- `libs/prompts/sbar_recommendation_v1.py`
- `libs/sbar/assessment_formatter.py`
- `services/pipeline_worker/app/services/sbar_orchestrator.py`

## Why a frozen transcript

The Assessment formatter is deterministic, so it can be checked by code.
The three LLM stages (Situation, Background, Recommendation) are not
deterministic. To make the regression suite reproducible we record the
expected LLM output per fixture (`llm_transcript:`) and the runner
substitutes it for live LLM calls. Reviewers then judge whether the
recorded transcript is clinically acceptable for the given inputs.

## Fixture format

Each `fixture-NN.yaml` is a single document with the following keys.

```yaml
id: SBAR-GS-NN              # required, matches filename
title: "..."                # short headline
clinical_scenario: |
  Free-text vignette read by the reviewer.

input:                      # SBARRequestPayload, minus run_id
  patient_id: "pat-..."
  situation:
    artifacts:
      - { type: referral_request, id: "rr-..." }
  background:
    - { type: encounter, id: "enc-..." }
  guideline_ids: ["G-..."]   # optional

resolved_situation:          # ResolvedSituation seed for resolve_situation()
  patient_id: "pat-..."
  patient_summary: { ... }
  artifacts: [ ... ]

resolved_background:         # list[ResolvedSource] seed
  - source_label: Encounter
    source_id: enc-...
    text: "..."
    codes:
      - { concept_id: "...", term: "...", assertion: present }

llm_transcript:              # canned LLM stage outputs (mocked)
  situation:    { markdown: "...", actions: [], error: null }
  background:   { markdown: "...", error: null }
  recommendation:
    markdown: "..."
    actions:
      - { action: "...", priority: 2ww, due_days: 14, rule_ids: ["..."] }
    error: null

evaluator_response:          # canned /terminology/guidelines/evaluate
  matched_rules: [ ... ]     # may be empty for no-match cases
  outage: false              # set true to simulate evaluator failure

reviewer_expectations:
  required_section_headings: ["## Situation", ...]
  required_phrases_in_assessment: [ ... ]
  required_phrases_in_recommendation: [ ... ]
  banned_phrases: [ ... ]
  # Each entry in required_phrases_* and banned_phrases may be either:
  #   - a bare string (substring match, case-sensitive), OR
  #   - a list of strings (any-of: passes if any one is found; for
  #     banned, none-of: passes if none are found).
  # Use the list form to express semantic equivalence, for example
  # ["2WW", "two-week wait", "two week wait"]. Keep the brittle literal
  # form for high-stakes tokens that the model MUST emit verbatim
  # (e.g. SNOMED rule_ids like "R-LUNG-001").
  expected_pathway_hints:
    rtr: "yes" | "no"                    # current formatter values
    rtr_evidence_contains: "..."         # optional substring match
    stt_contains: "two-week wait"        # optional substring match
    stt_evidence_contains: "R-..."       # optional substring match
    stt_is_null: true                    # optional, asserts stt absent
  expected_action_priority: "2ww"        # optional, checked against the recorded recommendation actions
  expected_status: "completed" | "draft" # optional, asserts SBARResult.status
  expected_errors_contain: "assessment:" # optional substring within errors[]
  reviewer_focus: |
    Plain-English notes for the human reviewer.
```

Note: today's `assessment_formatter._derive_pathway_hints` only emits
`rtr` of `"yes"` or `"no"` (no `"unknown"`). The orchestrator's
evaluator-outage branch sets `rtr="no"` with the exception string in
`rtr_evidence` and a `assessment:` entry in `errors[]`. Fixture-05
asserts on that combination as the discriminator.

## Running the suite

Run all 10 fixtures, write per-fixture reports under
`data/sbar-golden-set-reports/<UTC timestamp>/`:

```bash
python3 scripts/run_sbar_golden_set.py
```

Run a single fixture for fast iteration:

```bash
python3 scripts/run_sbar_golden_set.py --only fixture-04
```

Each report contains:

- `fixture.yaml` echo of the input
- `output.md` rendered SBAR (4 sections)
- `pathway_hints.json` derived `stt`/`rtr`/`alternative_pathway`
- `events.jsonl` per-stage progress events captured from the orchestrator
- `structural_check.json` pass/fail for every reviewer expectation

## Live LLM run (TC-009 step 3)

The deterministic offline runner above uses each fixture's recorded
`llm_transcript:` block. To exercise the SAME fixtures against the
real Bedrock model with the seeded production prompts:

```bash
.venv/bin/python scripts/run_sbar_live.py \
  --reports-dir evidence-bundles/LEO-AI/verification/VT-LEO-AI-189/live-run-<UTC>
```

Stages 1 (Situation), 2 (Background), and 4 (Recommendation) hit the
live model; stage 3 (Assessment) stays deterministic via
`libs.sbar.assessment_formatter.format_assessment` fed with each
fixture's canned `evaluator_response.matched_rules`. The fixture-05
outage flag is honoured exactly as the orchestrator handles it.

Per-fixture artefacts: `live_output.md` (composed SBAR),
`stages.json` (per-stage Markdown + actions + raw JSON + latency_ms),
`pathway_hints.json`, `structural_check.json`, plus a top-level
`live_summary.json`. Requires AWS Bedrock credentials in
`secrets/.env.secrets`.

## Reviewer sign-off

After the runner completes, walk the latest report directory with the
interactive harness:

```bash
# offline bundle (transcript-based)
python3 scripts/review_sbar_golden_set.py

# live bundle (real LLM)
python3 scripts/review_sbar_golden_set.py \
  --reports-dir evidence-bundles/LEO-AI/verification/VT-LEO-AI-189/live-run-<UTC>
```

The harness prints each fixture's vignette, the rendered SBAR, the
structural-check status, and prompts the reviewer for an explicit
pass/fail with a free-text comment. The signed ledger is written to
`<reports>/signed_ledger.json` and is the artefact the QA Lead attaches
to the VT-LEO-AI-189 evidence bundle.

A run is considered TC-009 pass when:

- Every structural check is `pass`, AND
- The reviewer marks every fixture `pass`, AND
- The signed ledger is countersigned by Clinical Safety Officer.

## Updating the suite

When prompts or the formatter change, re-run the runner first. If a
fixture's structural checks fail, the change has regressed. If the
checks pass but the reviewer rejects the rendered SBAR, update the
`llm_transcript:` to reflect the improved (and reviewer-approved)
output. Never edit `reviewer_expectations:` to make a failing run pass
without filing a CAPA.
