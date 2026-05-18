/**
 * VT-14819B16 - Advisory banner is fetched, displayed and non-dismissible.
 *
 * Atlas trace:
 *   DO: DO-3B62F38E
 *   DI: DI-3C06AFD0 AC3
 *   Risk mitigated: R-4965BCD2 (CSO override channel)
 */

import { AdvisoryClient } from "../release/advisory";

const ADVISORY_URL = "https://widget.example.test/v1/advisory.json";
const FORBIDDEN = /hide|dismiss|disable|suppress/i;

function _resp(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

describe("VT-14819B16 - advisory banner is non-dismissible", () => {
  test("renders an .leo-advisory banner with the headline + body when active", async () => {
    const fetcher = jest.fn().mockResolvedValue(
      _resp({
        active: true,
        severity: "safety",
        headline: "Withhold autosubmit",
        body: "Pending CSO review of source-record disclosure regression.",
      }),
    );
    const container = document.createElement("div");
    document.body.appendChild(container);
    const client = new AdvisoryClient({
      advisoryUrl: ADVISORY_URL,
      container,
      fetcher: fetcher as unknown as typeof fetch,
    });
    await client.refresh();

    const banner = container.querySelector(".leo-advisory");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("Withhold autosubmit");
    expect(banner?.textContent).toContain("CSO review");
  });

  test("rendered banner contains no dismiss / close / hide button", async () => {
    const fetcher = jest.fn().mockResolvedValue(
      _resp({ active: true, headline: "Test", body: "Body" }),
    );
    const container = document.createElement("div");
    const client = new AdvisoryClient({
      advisoryUrl: ADVISORY_URL,
      container,
      fetcher: fetcher as unknown as typeof fetch,
    });
    await client.refresh();
    const buttons = container.querySelectorAll("button");
    for (const btn of Array.from(buttons)) {
      const label = (btn.textContent ?? "") + (btn.getAttribute("aria-label") ?? "");
      expect(FORBIDDEN.test(label)).toBe(false);
    }
  });

  test("AdvisoryClient prototype exposes no method matching /hide|dismiss|disable|suppress/i", () => {
    const proto = AdvisoryClient.prototype as unknown as object;
    for (const name of Object.getOwnPropertyNames(proto)) {
      expect(FORBIDDEN.test(name)).toBe(false);
    }
  });

  test("inactive advisory does NOT render a banner", async () => {
    const fetcher = jest.fn().mockResolvedValue(_resp({ active: false }));
    const container = document.createElement("div");
    const client = new AdvisoryClient({
      advisoryUrl: ADVISORY_URL,
      container,
      fetcher: fetcher as unknown as typeof fetch,
    });
    await client.refresh();
    expect(container.querySelector(".leo-advisory")).toBeNull();
  });
});
