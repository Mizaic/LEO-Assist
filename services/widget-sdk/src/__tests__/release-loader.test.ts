/**
 * VT-0886D436 - Release loader picks active build within pinned major.
 *
 * Atlas trace:
 *   DO: DO-3B62F38E
 *   DI: DI-3C06AFD0 AC1 + AC2 (auto-update + CSO rollback)
 */

import { fetchActiveBuild } from "../release/loader";

const MANIFEST_URL = "https://widget.example.test/v1/manifest.json";

function _resp(body: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 502,
    statusText: ok ? "OK" : "Bad Gateway",
    json: async () => body,
  } as unknown as Response;
}

describe("VT-0886D436 - release loader picks active build within pinned major", () => {
  test("returns the active build when major matches", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValue(_resp({ major: 1, active: "1.4.2" }));
    const build = await fetchActiveBuild({
      manifestUrl: MANIFEST_URL,
      pinnedMajor: "1",
      fetcher: fetcher as unknown as typeof fetch,
    });
    expect(build).toBe("1.4.2");
    expect(fetcher).toHaveBeenCalledWith(
      MANIFEST_URL,
      expect.objectContaining({ method: "GET" }),
    );
  });

  test("after a CSO rollback the next call returns the new active hash", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce(_resp({ major: 1, active: "1.4.2" }))
      .mockResolvedValueOnce(_resp({ major: 1, active: "1.3.9" }));
    const args = {
      manifestUrl: MANIFEST_URL,
      pinnedMajor: "1",
      fetcher: fetcher as unknown as typeof fetch,
    };
    expect(await fetchActiveBuild(args)).toBe("1.4.2");
    expect(await fetchActiveBuild(args)).toBe("1.3.9");
  });

  test("rejects when manifest reports a different major", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValue(_resp({ major: 2, active: "2.0.0" }));
    await expect(
      fetchActiveBuild({
        manifestUrl: MANIFEST_URL,
        pinnedMajor: "1",
        fetcher: fetcher as unknown as typeof fetch,
      }),
    ).rejects.toThrow(/refusing to load build 2.0.0/);
  });

  test("rejects when manifest active hash does not start with pinned major", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValue(_resp({ major: 1, active: "9.9.9" }));
    await expect(
      fetchActiveBuild({
        manifestUrl: MANIFEST_URL,
        pinnedMajor: "1",
        fetcher: fetcher as unknown as typeof fetch,
      }),
    ).rejects.toThrow(/does not start with pinned major/);
  });
});
