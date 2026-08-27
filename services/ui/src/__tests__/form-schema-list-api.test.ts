/**
 * Live VT -- Settings form template list fetch.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
import { fetchFormSchemas } from "../app/settings/form-schemas/formSchemaApi";

describe("fetchFormSchemas", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("returns schemas from GET /api/form-schemas", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ schemas: [{ fingerprint: "fp-1", form_name: "Gynae" }] }),
    }) as typeof fetch;

    const rows = await fetchFormSchemas();
    expect(rows).toEqual([{ fingerprint: "fp-1", form_name: "Gynae" }]);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/form-schemas",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("returns an empty list when the API has no templates", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ schemas: [] }),
    }) as typeof fetch;

    await expect(fetchFormSchemas()).resolves.toEqual([]);
  });

  it("names the form teacher role on 403", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        detail: "One of these roles is required: validation, operations_manager",
      }),
    }) as typeof fetch;

    await expect(fetchFormSchemas()).rejects.toThrow(/form teacher role/);
  });

  it("keeps a retry message for other failures", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "boom" }),
    }) as typeof fetch;

    await expect(fetchFormSchemas()).rejects.toThrow(
      "Could not load form templates. Please retry.",
    );
  });
});
