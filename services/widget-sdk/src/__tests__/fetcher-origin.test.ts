/**
 * VT-D7751269 - Widget refuses to fetch any non-proxy origin.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416 AC2: "Widget refuses to issue a fetch to any
 *       origin other than the host's configured proxy origin."
 *
 * Stubs window.fetch and exercises the default fetcher path with
 * a matching and non-matching proxy origin against an explicit
 * allowlist.
 */

import {
  configureFetcher,
  fetchAssessment,
  type FetchAssessmentArgs,
} from "../data/fetcher";
import type { SbarAssessmentPayload } from "../data/types";

const ALLOWED_ORIGIN = "https://proxy.host.example";
const FOREIGN_ORIGIN = "https://attacker.example";

const PAYLOAD: SbarAssessmentPayload = {
  assessmentId: "ASSESS-1",
  tenantId: "tenant-A",
  generatedAt: "2026-04-20T00:00:00Z",
  markdown: "# Situation\nN/A\n",
  backgroundParts: [],
};

function _makeFetchStub(): jest.Mock {
  return jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => PAYLOAD,
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
