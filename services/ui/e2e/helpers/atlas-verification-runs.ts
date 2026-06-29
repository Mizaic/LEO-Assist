/**
 * Atlas verification-run REST helper.
 *
 * Records a verification-test run and uploads screenshot evidence via the
 * Atlas verification-runs REST API.  Mirrors atlas-validation-runs.ts so
 * Playwright VT specs follow the same pattern as VAL specs.
 *
 * Required env vars (set in services/ui/.env.local):
 *   ATLAS_VERIFICATION_RUNS_BASE_URL
 *     e.g. https://atlas.healthcarecopilot.ai/api/qms-graph/api/v1/verification-runs
 *   ATLAS_ORGANIZATION_ID   -- tenant UUID
 *   QMS_SERVICE_TOKEN       -- service token with verification-runs scope
 *
 * API contract:
 *   POST   {BASE}/                          create run -> { run_id }
 *   POST   {BASE}/{runId}/steps/{n}         record step result
 *   POST   {BASE}/{runId}/steps/{n}/evidence  upload evidence (multipart)
 *   PATCH  {BASE}/{runId}                   complete run
 *   GET    {BASE}/{runId}                   check run state
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { APIRequestContext } from "@playwright/test";

type VerificationResult = "pass" | "fail" | "blocked" | "not_applicable";

type CreateVerificationRunOptions = {
  vtId: string;
  environment?: string;
  executor?: string;
  metadata?: Record<string, unknown>;
};

type CompleteRunOptions = {
  summary?: string;
  failureReason?: string;
  completedAt?: string;
};

type EvidenceOptions = {
  fileName?: string;
  contentType?: string;
};

type MultipartFile = { name: string; mimeType: string; buffer: Buffer };
type MultipartValue = string | number | boolean | MultipartFile;

const REQUIRED_ENV = [
  "ATLAS_VERIFICATION_RUNS_BASE_URL",
  "ATLAS_ORGANIZATION_ID",
  "QMS_SERVICE_TOKEN",
] as const;

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function baseUrl(): string {
  return requiredEnv("ATLAS_VERIFICATION_RUNS_BASE_URL").replace(/\/$/, "");
}

export function authHeaders(): Record<string, string> {
  return {
    Authorization: `Bearer ${requiredEnv("QMS_SERVICE_TOKEN")}`,
    "X-Organization-ID": requiredEnv("ATLAS_ORGANIZATION_ID"),
  };
}

export function assertVerificationRunConfig(): void {
  for (const name of REQUIRED_ENV) {
    requiredEnv(name);
  }
}

export function isVerificationRunConfigured(): boolean {
  return REQUIRED_ENV.every((n) => Boolean(process.env[n]));
}

export function userFacingStepNumber(stepIndex: number): number {
  return stepIndex + 1;
}

export function buildFailureSummary(failingStepIndex: number): string {
  return `Test failed before step ${userFacingStepNumber(failingStepIndex)} completed.`;
}

export async function createVerificationRun(
  request: APIRequestContext,
  options: CreateVerificationRunOptions,
): Promise<string> {
  const response = await request.post(baseUrl(), {
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    timeout: 60_000,
    data: {
      vt_id: options.vtId,
      environment: options.environment ?? process.env.TEST_ENV ?? "local",
      executor: options.executor ?? "playwright",
      metadata: {
        git_sha: process.env.GITHUB_SHA,
        playwright_project: process.env.PLAYWRIGHT_PROJECT,
        ...options.metadata,
      },
    },
  });

  if (!response.ok()) {
    throw new Error(
      `create verification run failed: ${response.status()} ${await response.text()}`,
    );
  }

  const body = await response.json();
  return body.run_id as string;
}

export async function recordStep(
  request: APIRequestContext,
  runId: string,
  stepIndex: number,
  step: string,
  result: VerificationResult,
  notes?: string,
): Promise<void> {
  const response = await request.post(`${baseUrl()}/${runId}/steps/${stepIndex}`, {
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    timeout: 60_000,
    data: { step, result, notes },
  });

  if (!response.ok()) {
    throw new Error(
      `record verification step failed: ${response.status()} ${await response.text()}`,
    );
  }
}

export async function uploadEvidence(
  request: APIRequestContext,
  runId: string,
  stepIndex: number,
  filePathOrBuffer: string | Buffer,
  caption?: string,
  options: EvidenceOptions = {},
): Promise<void> {
  const isBuffer = Buffer.isBuffer(filePathOrBuffer);
  const bytes = isBuffer ? filePathOrBuffer : readFileSync(filePathOrBuffer);
  const fileName =
    options.fileName ?? (isBuffer ? undefined : path.basename(filePathOrBuffer));

  if (!fileName) {
    throw new Error(
      "uploadEvidence requires options.fileName when evidence is provided as a Buffer.",
    );
  }

  const contentType = options.contentType ?? "image/png";
  const sha256 = createHash("sha256").update(bytes).digest("hex");

  const multipart: Record<string, MultipartValue> = {
    file: { name: fileName, mimeType: contentType, buffer: bytes },
    content_type: contentType,
    sha256,
  };
  if (caption) {
    multipart.caption = caption;
  }

  const response = await request.post(
    `${baseUrl()}/${runId}/steps/${stepIndex}/evidence`,
    {
      headers: authHeaders(),
      timeout: 60_000,
      multipart,
    },
  );

  if (!response.ok()) {
    throw new Error(
      `upload verification evidence failed: ${response.status()} ${await response.text()}`,
    );
  }
}

export async function completeRun(
  request: APIRequestContext,
  runId: string,
  result: VerificationResult,
  options: CompleteRunOptions = {},
): Promise<void> {
  const response = await request.patch(`${baseUrl()}/${runId}`, {
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    timeout: 60_000,
    data: {
      result,
      summary: options.summary,
      failure_reason: options.failureReason,
      completed_at: options.completedAt ?? new Date().toISOString(),
    },
  });

  if (!response.ok()) {
    throw new Error(
      `complete verification run failed: ${response.status()} ${await response.text()}`,
    );
  }
}

export async function failAndComplete(
  request: APIRequestContext,
  runId: string,
  error: unknown,
  failingStepIndex: number,
): Promise<void> {
  const message = error instanceof Error ? error.message : String(error);
  const stack =
    error instanceof Error ? error.stack?.split("\n").slice(0, 5).join("\n") : undefined;

  await completeRun(request, runId, "fail", {
    summary: buildFailureSummary(failingStepIndex),
    failureReason: stack ? `${message}\n${stack}` : message,
  });
}

export async function ensureRunNotLeftRunning(
  request: APIRequestContext,
  runId: string | undefined,
  lastCompletedStep: number,
): Promise<void> {
  if (!runId) {
    return;
  }

  const response = await request.get(`${baseUrl()}/${runId}`, {
    headers: authHeaders(),
    timeout: 60_000,
  });
  if (!response.ok()) {
    return;
  }

  const body = await response.json();
  if (body.status === "running") {
    await failAndComplete(
      request,
      runId,
      new Error("Suite ended without completing the verification run."),
      lastCompletedStep + 1,
    );
  }
}
