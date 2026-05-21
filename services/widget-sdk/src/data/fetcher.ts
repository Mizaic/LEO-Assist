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

export interface FetchAssessmentArgs {
  assessmentId: string;
  widgetToken: string;
  proxyOrigin: string;
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

function _assertAllowedOrigin(args: FetchAssessmentArgs): string {
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
