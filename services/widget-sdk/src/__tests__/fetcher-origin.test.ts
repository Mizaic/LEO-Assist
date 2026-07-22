/**
 * VT-D7751269 - Widget refuses to fetch any non-proxy origin.
 * VT-EEF7F2C6 - Fetcher normalises snake_case API response to camelCase.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416 AC2: "Widget refuses to issue a fetch to any
 *       origin other than the host's configured proxy origin."
 *   DI: DI-AF2C3996 AC1: snake_case -> camelCase normalisation.
 *
 * Stubs window.fetch and exercises the default fetcher path with
 * a matching and non-matching proxy origin against an explicit
 * allowlist.
 */

import {
  configureFetcher,
  configureSourceTextFetcher,
  fetchAssessment,
  fetchSourceText,
  normalisePayload,
  type FetchAssessmentArgs,
  type FetchSourceTextArgs,
} from "../data/fetcher";

const ALLOWED_ORIGIN = "https://proxy.host.example";
const FOREIGN_ORIGIN = "https://attacker.example";

// The API returns snake_case. The widget expects camelCase. The mock
// must use snake_case to exercise the real normalisation path.
const SNAKE_CASE_RESPONSE = {
  assessment_id: "ASSESS-1",
  tenant_id: "tenant-A",
  generated_at: "2026-04-20T00:00:00Z",
  markdown: "## situation\nN/A\n",
  background_parts: [],
  guideline_matches: [
    {
      rule_id: "rule:NG12:v1:R004:abc",
      name: "Chest X-ray within 2 weeks",
      strength: "offer",
      guideline_id: "NG12",
      recommendation_verbatim: "Offer an urgent chest X-ray.",
    },
  ],
  completeness_findings: null,
};

function _makeFetchStub(): jest.Mock {
  return jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => SNAKE_CASE_RESPONSE,
  });
}

describe("fetchAssessment proxy-origin guard - DI-A1206416 AC2", () => {
  let originalFetch: typeof fetch;
  let stub: jest.Mock;

  beforeEach(() => {
    configureFetcher(null);
    originalFetch = global.fetch;
    stub = _makeFetchStub();
    global.fetch = stub as unknown as typeof fetch;
  });

  afterEach(() => {
    configureFetcher(null);
    global.fetch = originalFetch;
  });

  function _args(overrides: Partial<FetchAssessmentArgs>): FetchAssessmentArgs {
    return {
      assessmentId: "ASSESS-1",
      widgetToken: "ignored-by-test",
      proxyOrigin: ALLOWED_ORIGIN,
      allowedProxyOrigins: [ALLOWED_ORIGIN],
      ...overrides,
    };
  }

  test("AC2.a calls fetch when proxy origin is in the allowlist", async () => {
    const result = await fetchAssessment(_args({}));
    expect(stub).toHaveBeenCalledTimes(1);
    expect(stub.mock.calls[0][0]).toBe(`${ALLOWED_ORIGIN}/sdk/sbar/ASSESS-1`);
    expect(result.assessmentId).toBe("ASSESS-1");
  });

  test("AC2.b refuses and never calls fetch when proxy origin is foreign", async () => {
    await expect(
      fetchAssessment(_args({ proxyOrigin: FOREIGN_ORIGIN })),
    ).rejects.toThrow("leo-widget: refusing to fetch from non-proxy origin");
    expect(stub).not.toHaveBeenCalled();
  });

  test("AC2.c sends Bearer widget-token in Authorization header", async () => {
    await fetchAssessment(_args({ widgetToken: "tok-xyz" }));
    const init = stub.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok-xyz");
  });
});

describe("fetchSourceText proxy-origin guard - DI-A898556B AC3", () => {
  let originalFetch: typeof fetch;
  let stub: jest.Mock;

  beforeEach(() => {
    configureSourceTextFetcher(null);
    originalFetch = global.fetch;
    stub = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "chunk-1",
        type: "Chunk",
        label: "Referral letter chunk 1",
        text: "Dear Colleague,\n\nFull letter text.",
      }),
    });
    global.fetch = stub as unknown as typeof fetch;
  });

  afterEach(() => {
    configureSourceTextFetcher(null);
    global.fetch = originalFetch;
  });

  function _args(overrides: Partial<FetchSourceTextArgs>): FetchSourceTextArgs {
    return {
      assessmentId: "ASSESS-1",
      sourceId: "chunk-1",
      widgetToken: "ignored-by-test",
      proxyOrigin: ALLOWED_ORIGIN,
      allowedProxyOrigins: [ALLOWED_ORIGIN],
      ...overrides,
    };
  }

  test("calls the assessment-scoped sources endpoint with Bearer auth", async () => {
    const result = await fetchSourceText(_args({ widgetToken: "tok-xyz" }));
    expect(stub).toHaveBeenCalledTimes(1);
    expect(stub.mock.calls[0][0]).toBe(
      `${ALLOWED_ORIGIN}/sdk/sbar/ASSESS-1/sources/chunk-1`,
    );
    const init = stub.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok-xyz");
    expect(result.text).toBe("Dear Colleague,\n\nFull letter text.");
  });

  test("refuses and never calls fetch when proxy origin is foreign", async () => {
    await expect(
      fetchSourceText(_args({ proxyOrigin: FOREIGN_ORIGIN })),
    ).rejects.toThrow("leo-widget: refusing to fetch from non-proxy origin");
    expect(stub).not.toHaveBeenCalled();
  });

  test("rejects when the response is not ok", async () => {
    stub.mockResolvedValue({ ok: false, status: 404 });
    await expect(fetchSourceText(_args({}))).rejects.toThrow(
      "leo-widget: source text fetch failed (404)",
    );
  });
});

describe("normalisePayload - snake_case to camelCase - DI-AF2C3996", () => {
  test("maps top-level fields to camelCase", () => {
    const result = normalisePayload(SNAKE_CASE_RESPONSE as Record<string, unknown>);
    expect(result.assessmentId).toBe("ASSESS-1");
    expect(result.tenantId).toBe("tenant-A");
    expect(result.generatedAt).toBe("2026-04-20T00:00:00Z");
    expect(result.markdown).toBe("## situation\nN/A\n");
    expect(result.backgroundParts).toEqual([]);
  });

  test("maps guideline_matches entries to camelCase GuidelineMatch", () => {
    const result = normalisePayload(SNAKE_CASE_RESPONSE as Record<string, unknown>);
    expect(result.guidelineMatches).toHaveLength(1);
    const m = result.guidelineMatches![0];
    expect(m.ruleId).toBe("rule:NG12:v1:R004:abc");
    expect(m.name).toBe("Chest X-ray within 2 weeks");
    expect(m.strength).toBe("offer");
    expect(m.guidelineId).toBe("NG12");
    expect(m.recommendationVerbatim).toBe("Offer an urgent chest X-ray.");
  });

  test("maps null completeness_findings to null completenessFinding", () => {
    const result = normalisePayload(SNAKE_CASE_RESPONSE as Record<string, unknown>);
    expect(result.completenessFinding).toBeNull();
  });

  test("maps absent guideline_matches to empty array", () => {
    const raw = { ...SNAKE_CASE_RESPONSE, guideline_matches: undefined };
    const result = normalisePayload(raw as Record<string, unknown>);
    expect(result.guidelineMatches).toEqual([]);
  });
});
