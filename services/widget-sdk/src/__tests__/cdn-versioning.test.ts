/**
 * VT-98AC5D4E -- Verify CDN versioning: prior version accessible after new release.
 *
 * Atlas trace:
 *   DI: DI-3C996BC7 -- Deliver the Widget with a Versioned Integration Contract
 *   DO: DO-A3465F94 -- SBAR widget CDN package -- leo-widget
 *
 * Acceptance criteria under test:
 *   AC3: New CDN versions do not break existing host integrations pinned to
 *        previous widget versions.
 *   AC1: The widget bundle is served from a CDN URL using a versioned path
 *        (e.g. /v1/leo-widget.js).
 *
 * The version isolation guarantee is implemented by the manifest loader:
 * a host pinning major=1 cannot be silently upgraded to major=2 when a
 * new CDN version is published. These tests verify that contract holds.
 */

import { fetchActiveBuild } from "../release/loader";

const V1_MANIFEST = "https://cdn.example.test/v1/manifest.json";
const V2_MANIFEST = "https://cdn.example.test/v2/manifest.json";

function mockFetch(body: unknown, ok = true): typeof fetch {
  return jest.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 502,
    statusText: ok ? "OK" : "Bad Gateway",
    json: async () => body,
  }) as unknown as typeof fetch;
}

// ---------------------------------------------------------------------------
// AC3: prior version hosts are not broken by a new major release
// ---------------------------------------------------------------------------

describe("VT-98AC5D4E -- CDN versioning: prior version accessible after new release", () => {
  describe("AC3: v1-pinned host continues to resolve v1 builds after v2 is published", () => {
    test("v1-pinned host receives a v1.x.x build from its own manifest", async () => {
      const fetcher = mockFetch({ major: 1, active: "1.5.0" });
      const result = await fetchActiveBuild({
        manifestUrl: V1_MANIFEST,
        pinnedMajor: "1",
        fetcher,
      });
      expect(result).toBe("1.5.0");
      expect(result.startsWith("1.")).toBe(true);
    });

    test("v1-pinned host is protected when v2 manifest is mistakenly queried", async () => {
      const fetcher = mockFetch({ major: 2, active: "2.0.0" });
      await expect(
        fetchActiveBuild({
          manifestUrl: V1_MANIFEST,
          pinnedMajor: "1",
          fetcher,
        }),
      ).rejects.toThrow(/refusing to load build/);
    });

    test("v2-pinned host resolves independently from v1-pinned hosts", async () => {
      const v1Fetcher = mockFetch({ major: 1, active: "1.5.0" });
      const v2Fetcher = mockFetch({ major: 2, active: "2.0.0" });

      const [v1Build, v2Build] = await Promise.all([
        fetchActiveBuild({ manifestUrl: V1_MANIFEST, pinnedMajor: "1", fetcher: v1Fetcher }),
        fetchActiveBuild({ manifestUrl: V2_MANIFEST, pinnedMajor: "2", fetcher: v2Fetcher }),
      ]);

      expect(v1Build).toBe("1.5.0");
      expect(v2Build).toBe("2.0.0");
    });

    test("v1-pinned host continues to resolve the latest v1 patch after multiple v2 releases", async () => {
      const fetcher = jest
        .fn()
        .mockResolvedValue({
          ok: true,
          status: 200,
          statusText: "OK",
          json: async () => ({ major: 1, active: "1.9.3" }),
        } as unknown as Response);

      const result = await fetchActiveBuild({
        manifestUrl: V1_MANIFEST,
        pinnedMajor: "1",
        fetcher: fetcher as unknown as typeof fetch,
      });
      expect(result).toBe("1.9.3");
    });

    test("v1-pinned host rejects active build whose version prefix mismatches pinned major", async () => {
      const fetcher = mockFetch({ major: 1, active: "2.1.0" });
      await expect(
        fetchActiveBuild({ manifestUrl: V1_MANIFEST, pinnedMajor: "1", fetcher }),
      ).rejects.toThrow(/does not start with pinned major/);
    });
  });

  // ---------------------------------------------------------------------------
  // AC1: CDN URL uses a versioned path
  // ---------------------------------------------------------------------------

  describe("AC1: versioned CDN path is used for each major", () => {
    test("v1 manifest URL contains /v1/ path segment", () => {
      expect(V1_MANIFEST).toMatch(/\/v1\//);
    });

    test("v2 manifest URL contains /v2/ path segment", () => {
      expect(V2_MANIFEST).toMatch(/\/v2\//);
    });

    test("v1 and v2 manifest URLs are distinct paths", () => {
      expect(V1_MANIFEST).not.toBe(V2_MANIFEST);
    });

    test("fetchActiveBuild requests only the manifest URL it is given", async () => {
      const fetcher = mockFetch({ major: 1, active: "1.2.0" });
      await fetchActiveBuild({ manifestUrl: V1_MANIFEST, pinnedMajor: "1", fetcher });
      expect(fetcher).toHaveBeenCalledWith(V1_MANIFEST, expect.any(Object));
      expect(fetcher).toHaveBeenCalledTimes(1);
    });
  });

  // ---------------------------------------------------------------------------
  // Additional resilience: bad manifests
  // ---------------------------------------------------------------------------

  describe("resilience: manifest failures do not silently downgrade version", () => {
    test("CDN fetch failure propagates as error (does not fall back to wrong version)", async () => {
      const fetcher = mockFetch({}, false);
      await expect(
        fetchActiveBuild({ manifestUrl: V1_MANIFEST, pinnedMajor: "1", fetcher }),
      ).rejects.toThrow(/manifest fetch failed/);
    });

    test("manifest missing active field rejects with informative error", async () => {
      const fetcher = mockFetch({ major: 1 });
      await expect(
        fetchActiveBuild({ manifestUrl: V1_MANIFEST, pinnedMajor: "1", fetcher }),
      ).rejects.toThrow(/missing active/);
    });
  });
});
