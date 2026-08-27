/**
 * VT -- form fingerprint helper calls the API.
 *
 * Atlas trace: DI-5C9CA57B
 */
import { computeFormFingerprint } from "../components/operations/formSchemaFingerprint";

describe("computeFormFingerprint", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("returns fingerprint from POST /api/form-schemas/fingerprint", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ fingerprint: "abc123def4567890" }),
    }) as typeof fetch;

    const fp = await computeFormFingerprint("Section A: test form with []");
    expect(fp).toBe("abc123def4567890");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/form-schemas/fingerprint",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws plain English when the API fails", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Text too short" }),
    }) as typeof fetch;

    await expect(computeFormFingerprint("short")).rejects.toThrow(
      "Text too short",
    );
  });
});
