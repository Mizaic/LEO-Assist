---
name: playwright-validation-runs
description: Build Playwright validation tests that record Atlas validation execution runs and upload step-level evidence through the validation-runs REST API. Use when creating or editing Playwright VAL specs, Atlas execution run helpers, step evidence uploads, or CI validation runs for LEO Clinical Decision Support.
---

# Playwright Validation Runs

## Use This For

- Playwright VAL specs under `services/ui/e2e/val-*.spec.ts` and `services/widget-sdk/e2e/val-*.spec.ts`
- Helpers in `services/ui/e2e/helpers/` and `services/widget-sdk/e2e/helpers/`
- Step-level screenshots and evidence upload
- Local or CI validation runs against LEO UI or widget demo host

## Core Rule

Playwright records validation execution through REST, not MCP.

MCP is for design-control authoring. Playwright is for execution runs and evidence.

## Required Environment

Set in `services/ui/.env.local` (widget-sdk also reads this path):

```text
ATLAS_VALIDATION_RUNS_BASE_URL=https://atlas.healthcarecopilot.ai/api/qms-graph/api/v1/validation-runs
ATLAS_ORGANIZATION_ID=<tenant uuid>
QMS_SERVICE_TOKEN=<service token>
```

Never commit or print tokens.

## API Contract

Use these endpoints:

- `POST {BASE}` creates a run.
- `POST {BASE}/{runId}/steps/{stepIndex}` records a step.
- `POST {BASE}/{runId}/steps/{stepIndex}/evidence` uploads multipart evidence.
- `PATCH {BASE}/{runId}` completes the run.
- `GET {BASE}/{runId}` checks run state for safety cleanup.

Headers for every request:

```text
Authorization: Bearer <QMS_SERVICE_TOKEN>
X-Organization-ID: <ATLAS_ORGANIZATION_ID>
```

## Step Index Rule

The API uses zero-based indices:

- Protocol step 1 -> `step_index: 0`
- Protocol step 2 -> `step_index: 1`

Use one-based numbers only in user-facing text.

## Helper Conventions

Use `runValTest()` from `validation-spec-runner.ts`:

```ts
await runValTest(page, request, testInfo, {
  valId: "VAL-XXXXXXXX",
  targetUrl: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
  metadata: { atlas_un_id: "UN-XXXXXXXX" },
  protocol: PROTOCOL,
  body: async (ctx) => {
    // execute steps, call recordProtocolStep, update ctx.lastCompletedStep.value
    await finishValPass(ctx.request, ctx.runId, "summary");
  },
});
```

Lower-level helpers:

```ts
createValidationRun(request, { valTestId, targetUrl, metadata })
recordStep(request, runId, stepIndex, step, result, notes)
uploadEvidence(request, runId, stepIndex, filePathOrBuffer, caption, options)
completeRun(request, runId, result, { summary, failureReason })
failAndComplete(request, runId, error, failingStepIndex)
ensureRunNotLeftRunning(request, runId, lastCompletedStep)
blockRun(request, runId, step, reason)
```

## Test Structure

Use one run per VAL protocol suite via `runValTest()`:

1. Create run before steps (handled by runner).
2. Stub routes or sign in as needed to reach the feature.
3. Execute a protocol step.
4. Call `recordProtocolStep()` with screenshot evidence.
5. Update `ctx.lastCompletedStep.value`.
6. Call `finishValPass()` when all automated steps pass.
7. On failure, runner calls `failAndComplete()` and re-throws.
8. Runner calls `ensureRunNotLeftRunning()` in `finally`.

## Setup Versus Evidence

Treat sign-in, seeded data, and navigation as setup when they are only needed to reach the VAL start point.

- Do not record login screenshots as protocol evidence unless the VAL validates sign-in.
- Start `recordProtocolStep()` at the first step that proves the VAL outcome.

## Source Grounding

Before implementing a Playwright validation test, inspect the LEO repo:

- UI routes and pages under `services/ui/src/`
- Widget demo host under `services/widget-sdk/demo/`
- Existing VT e2e specs under `services/ui/e2e/` for stub patterns

Use Atlas to understand the regulated intent. Use source code and live UI to implement checks.

## Provenance

Each Playwright validation test should include tags or annotations for:

- Atlas VAL id (`@VAL-XXXXXXXX`)
- Atlas UN id (`@UN-XXXXXXXX`)

Example:

```ts
tag: ["@UN-3B25A20E", "@VAL-4D70E63C"]
annotation: [{ type: "Atlas VAL", description: "VAL-4D70E63C - ..." }]
```

## Result Values

Use lowercase:

- `pass`
- `fail`
- `blocked`
- `not_applicable`

Use `blockRun()` + `ValidationBlockedError` when a VAL cannot be proven honestly (missing fixture, staging data, etc.). Playwright should still fail CI for blocked runs.

## Run Commands

```bash
cd services/ui && npm run e2e:val
cd services/widget-sdk && npm run e2e:val
```

Specs skip when Atlas env is missing. Populate `services/ui/.env.local` for local recording.

## Reference Implementation

The MediViewer validation harness at `MIZAIC_MV_VALIDATION_TESTS` is the upstream pattern this repo follows.
