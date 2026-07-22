/**
 * Assessment fetcher for the LEO widget.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F (origin allowlist + bearer-token fetch)
 *   DI: DI-A1206416 (host-proxied short-lived widget tokens; the
 *       widget never calls the LEO API directly from the browser)
 *
 * The widget calls a SINGLE host-controlled proxy origin. Any
 * attempt (caller error or hostile reconfiguration) to fetch from
 * a different origin is rejected before fetch() is invoked. This
 * is the browser-side belt-and-braces companion to the server-side
 * /sdk/sbar/ assessment-id check.
 */

import type {
  CompletenessFinding,
  GuidelineMatch,
  SbarAssessmentPayload,
  SbarBackgroundPart,
} from "./types";

interface OriginGuardedArgs {
  proxyOrigin: string;
  allowedProxyOrigins?: readonly string[];
}

export interface FetchAssessmentArgs extends OriginGuardedArgs {
  assessmentId: string;
  widgetToken: string;
  /**
   * Optional allowlist of acceptable proxy origins. Defaults to
   * [args.proxyOrigin] (single allowed origin per widget instance).
   * Tests and host integrators MAY pass an explicit allowlist.
   */
  allowedProxyOrigins?: readonly string[];
}

export type FetchAssessmentFn = (
  args: FetchAssessmentArgs,
) => Promise<SbarAssessmentPayload>;

export interface FetchSourceTextArgs extends OriginGuardedArgs {
  assessmentId: string;
  sourceId: string;
  widgetToken: string;
}

export interface SourceTextResult {
  id: string;
  type: string;
  label: string;
  text: string;
}

export type FetchSourceTextFn = (
  args: FetchSourceTextArgs,
) => Promise<SourceTextResult>;

/**
 * Normalise a raw snake_case API response into the camelCase widget
 * payload. The LEO API uses Python snake_case conventions; the widget
 * contract is camelCase. This is the single place where the mapping
 * is applied so the rest of the widget never sees raw API field names.
 */
export function normalisePayload(
  raw: Record<string, unknown>,
): SbarAssessmentPayload {
  const rawMatches = (
    (raw["guideline_matches"] ?? []) as Array<Record<string, unknown>>
  ).map(
    (m): GuidelineMatch => ({
      ruleId: m["rule_id"] as string,
      name: m["name"] as string,
      strength: m["strength"] as string,
      guidelineId: m["guideline_id"] as string,
      recommendationVerbatim: (m["recommendation_verbatim"] ?? null) as
        | string
        | null,
    }),
  );

  const rawCompleteness = raw["completeness_findings"] as
    | CompletenessFinding
    | null
    | undefined;

  return {
    assessmentId: raw["assessment_id"] as string,
    tenantId: raw["tenant_id"] as string,
    generatedAt: raw["generated_at"] as string,
    markdown: raw["markdown"] as string,
    backgroundParts: (raw["background_parts"] ?? []) as SbarBackgroundPart[],
    patientReferenceLabel: raw["patient_reference_label"] as
      | string
      | undefined,
    guidelineMatches: rawMatches,
    completenessFinding: rawCompleteness ?? null,
  };
}

let _impl: FetchAssessmentFn | null = null;

export function configureFetcher(impl: FetchAssessmentFn | null): void {
  _impl = impl;
}

function _normaliseOrigin(value: string): string {
  try {
    return new URL(value).origin;
  } catch {
    throw new Error(
      `leo-widget: invalid proxy origin '${value}' (not a parseable URL)`,
    );
  }
}

function _assertAllowedOrigin(args: OriginGuardedArgs): string {
  const requested = _normaliseOrigin(args.proxyOrigin);
  const allowlist = (args.allowedProxyOrigins ?? [args.proxyOrigin]).map(
    _normaliseOrigin,
  );
  if (!allowlist.includes(requested)) {
    throw new Error("leo-widget: refusing to fetch from non-proxy origin");
  }
  return requested;
}

async function _defaultFetcher(
  args: FetchAssessmentArgs,
): Promise<SbarAssessmentPayload> {
  const origin = _assertAllowedOrigin(args);
  const url = `${origin}/sdk/sbar/${encodeURIComponent(args.assessmentId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${args.widgetToken}`,
      Accept: "application/json",
    },
    credentials: "omit",
    mode: "cors",
  });
  if (!res.ok) {
    throw new Error(`leo-widget: assessment fetch failed (${res.status})`);
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return normalisePayload(raw);
}

export async function fetchAssessment(
  args: FetchAssessmentArgs,
): Promise<SbarAssessmentPayload> {
  const fn = _impl ?? _defaultFetcher;
  return fn(args);
}

let _sourceTextImpl: FetchSourceTextFn | null = null;

/** Test / demo seam, mirrors ``configureFetcher``. */
export function configureSourceTextFetcher(impl: FetchSourceTextFn | null): void {
  _sourceTextImpl = impl;
}

/**
 * Live lookup for a single source record's exact text, used by the
 * source-record dialog when the persisted background part has no
 * ``fullText`` (Assessments generated before that field existed).
 * Same origin allowlist and Bearer-token contract as
 * ``fetchAssessment`` -- the widget still never talks to Neo4j or the
 * LEO API directly, only the host-controlled proxy origin.
 */
async function _defaultSourceTextFetcher(
  args: FetchSourceTextArgs,
): Promise<SourceTextResult> {
  const origin = _assertAllowedOrigin(args);
  const url =
    `${origin}/sdk/sbar/${encodeURIComponent(args.assessmentId)}` +
    `/sources/${encodeURIComponent(args.sourceId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${args.widgetToken}`,
      Accept: "application/json",
    },
    credentials: "omit",
    mode: "cors",
  });
  if (!res.ok) {
    throw new Error(`leo-widget: source text fetch failed (${res.status})`);
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    id: String(raw["id"] ?? args.sourceId),
    type: String(raw["type"] ?? "Record"),
    label: String(raw["label"] ?? args.sourceId),
    text: String(raw["text"] ?? ""),
  };
}

export async function fetchSourceText(
  args: FetchSourceTextArgs,
): Promise<SourceTextResult> {
  const fn = _sourceTextImpl ?? _defaultSourceTextFetcher;
  return fn(args);
}
