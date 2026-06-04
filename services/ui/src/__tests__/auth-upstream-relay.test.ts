import * as fs from "fs";
import * as path from "path";
import { fetchAuthUpstream } from "@/lib/authUpstreamRelay";
import { serverFetch } from "@/lib/serverFetch";

jest.mock("@/lib/serverFetch", () => ({
  serverFetch: jest.fn(),
}));

const SRC_ROOT = path.resolve(__dirname, "..");
const mockServerFetch = serverFetch as jest.MockedFunction<typeof serverFetch>;

function read(rel: string): string {
  return fs.readFileSync(path.join(SRC_ROOT, rel), "utf-8");
}

function mockResponse(
  status: number,
  headers: Record<string, string | string[]>,
): Response {
  return {
    status,
    headers: {
      get(name: string): string | null {
        const value = headers[name.toLowerCase()];
        return Array.isArray(value) ? value[0] : value ?? null;
      },
      getSetCookie(): string[] {
        const value = headers["set-cookie"];
        if (!value) return [];
        return Array.isArray(value) ? value : [value];
      },
    },
  } as unknown as Response;
}

describe("auth upstream relay (ACA login parity)", () => {
  const originalInternalApiBase = process.env.INTERNAL_API_BASE;

  afterEach(() => {
    process.env.INTERNAL_API_BASE = originalInternalApiBase;
    mockServerFetch.mockReset();
  });

  test("TC-001: follows ACA same-host HTTP-to-HTTPS redirects server-side", async () => {
    process.env.INTERNAL_API_BASE =
      "http://core-api.proudriver-82c5b80a.uksouth.azurecontainerapps.io";
    mockServerFetch
      .mockResolvedValueOnce(
        mockResponse(301, {
          location:
            "https://core-api.proudriver-82c5b80a.uksouth.azurecontainerapps.io/auth/login?next_url=%2Fcare%2Fdashboard",
        }),
      )
      .mockResolvedValueOnce(
        mockResponse(302, {
          location:
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
          "set-cookie": "leo_oauth_nonce=abc; HttpOnly; Secure; Path=/",
        }),
      );

    const upstream = await fetchAuthUpstream(
      "http://core-api.proudriver-82c5b80a.uksouth.azurecontainerapps.io/auth/login?next_url=%2Fcare%2Fdashboard",
      "",
    );

    expect(mockServerFetch).toHaveBeenCalledTimes(2);
    expect(upstream.response.headers.get("location")).toBe(
      "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    );
    expect(upstream.setCookieHeaders).toContain(
      "leo_oauth_nonce=abc; HttpOnly; Secure; Path=/",
    );
  });

  test("TC-002: shared helper keeps external redirects browser-facing", () => {
    const src = read("lib/authUpstreamRelay.ts");
    expect(src).toMatch(/fetchAuthUpstream/);
    expect(src).toMatch(/next\.host !== apiHost/);
    expect(src).toMatch(/redirect:\s*"manual"/);
  });

  test("TC-003: login route uses fetchAuthUpstream not bare fetch", () => {
    const src = read("app/auth/login/route.ts");
    expect(src).toMatch(/fetchAuthUpstream/);
    expect(src).not.toMatch(/await fetch\(/);
  });

  test("TC-004: callback route uses fetchAuthUpstream not bare fetch", () => {
    const src = read("app/auth/callback/route.ts");
    expect(src).toMatch(/fetchAuthUpstream/);
    expect(src).not.toMatch(/await fetch\(/);
  });
});
