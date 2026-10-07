/**
 * Teach this form must preload a library schema by live org/service ids
 * when the letter-content fingerprint misses.
 *
 * RK5 / 7980224 are fixture values only. Production code must use the
 * ids passed from the review payload.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
import * as fs from "fs";
import * as path from "path";

import {
  loadTaughtLibrarySchema,
  savedSchemaBlocksAutoDetect,
} from "../components/operations/formSchemaTeach";

const OPS = path.join(__dirname, "../components/operations");

const LIBRARY_SECTIONS = [
  {
    section_id: "A",
    section_type: "checkbox_single",
    label: "Cancer type suspected",
    start_pattern: "Section A",
    items: [{ pattern: "Cervix", entity_text: "Cervical cancer" }],
  },
];

function jsonOk(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

describe("loadTaughtLibrarySchema -- org and service ids, not letter hash", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("loads library sections when letter fingerprint misses but org and service ids hit", async () => {
    const letterHash = "abc123def4567890";
    const orgId = "RK5";
    const serviceId = "7980224";
    const libraryFp = "sfh-gynae-2ww-v1";

    global.fetch = jest.fn().mockImplementation((url: string) => {
      const href = String(url);
      if (href.startsWith(`/api/form-schemas/${letterHash}`)) {
        return Promise.resolve(jsonOk({ schema: null, match: "none" }));
      }
      if (
        href.startsWith("/api/form-schemas?") &&
        href.includes(`organization_id=${orgId}`) &&
        href.includes(`service_id=${serviceId}`)
      ) {
        return Promise.resolve(
          jsonOk({
            schemas: [
              {
                fingerprint: libraryFp,
                organization_id: orgId,
                service_id: serviceId,
                form_name: "SFH Gynae 2WW",
              },
            ],
          }),
        );
      }
      if (href.startsWith(`/api/form-schemas/${libraryFp}`)) {
        return Promise.resolve(
          jsonOk({
            schema: {
              form_name: "SFH Gynae 2WW",
              fingerprint: libraryFp,
              sections: LIBRARY_SECTIONS,
            },
            match: "fingerprint",
          }),
        );
      }
      return Promise.resolve(jsonOk({ schemas: [], schema: null }));
    }) as typeof fetch;

    const loaded = await loadTaughtLibrarySchema(letterHash, {
      organizationId: orgId,
      serviceId: serviceId,
    });

    expect(loaded).not.toBeNull();
    expect(loaded?.fingerprint).toBe(libraryFp);
    expect(loaded?.form_name).toBe("SFH Gynae 2WW");
    expect(loaded?.sections).toHaveLength(1);
    expect(savedSchemaBlocksAutoDetect(loaded?.sections ?? [])).toBe(true);
    const listCall = (global.fetch as jest.Mock).mock.calls
      .map((call) => String(call[0]))
      .find((href) => href.startsWith("/api/form-schemas?"));
    expect(listCall).toContain(`organization_id=${orgId}`);
    expect(listCall).toContain(`service_id=${serviceId}`);
  });

  it("uses caller-supplied ids, not a hardcoded trust", async () => {
    const letterHash = "ffffffffffffffff";
    const orgId = "org-trust-x";
    const serviceId = "svc-clinic-y";
    const libraryFp = "trust-x-clinic-y-v1";

    global.fetch = jest.fn().mockImplementation((url: string) => {
      const href = String(url);
      if (href.startsWith(`/api/form-schemas/${letterHash}`)) {
        return Promise.resolve(jsonOk({ schema: null, match: "none" }));
      }
      if (
        href.startsWith("/api/form-schemas?") &&
        href.includes(`organization_id=${orgId}`) &&
        href.includes(`service_id=${serviceId}`)
      ) {
        return Promise.resolve(
          jsonOk({
            schemas: [
              {
                fingerprint: libraryFp,
                organization_id: orgId,
                service_id: serviceId,
                form_name: "Clinic Y form",
              },
            ],
          }),
        );
      }
      if (href.startsWith(`/api/form-schemas/${libraryFp}`)) {
        return Promise.resolve(
          jsonOk({
            schema: {
              form_name: "Clinic Y form",
              fingerprint: libraryFp,
              sections: LIBRARY_SECTIONS,
            },
          }),
        );
      }
      return Promise.resolve(jsonOk({ schemas: [], schema: null }));
    }) as typeof fetch;

    const loaded = await loadTaughtLibrarySchema(letterHash, {
      organizationId: orgId,
      serviceId: serviceId,
    });

    expect(loaded?.fingerprint).toBe(libraryFp);
    expect(loaded?.form_name).toBe("Clinic Y form");
    const listed = (global.fetch as jest.Mock).mock.calls.map((call) =>
      String(call[0]),
    );
    expect(listed.some((href) => href.includes("RK5"))).toBe(false);
    expect(listed.some((href) => href.includes("7980224"))).toBe(false);
  });

  it("returns null when org and service ids miss as well", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      jsonOk({ schema: null, match: "none", schemas: [] }),
    ) as typeof fetch;

    const loaded = await loadTaughtLibrarySchema("deadbeefdeadbeef", {
      organizationId: "org-none",
      serviceId: "svc-none",
    });
    expect(loaded).toBeNull();
  });
});

describe("Teach this form source does not hardcode a trust", () => {
  const teachFiles = [
    "formSchemaTeach.ts",
    "useFormSchemaTeach.ts",
    "FormSchemaAnnotator.tsx",
    "ExtractionQualityReviewDialog.tsx",
  ];

  it.each(teachFiles)("%s has no hardcoded Sherwood or ODS ids", (name) => {
    const src = fs.readFileSync(path.join(OPS, name), "utf8");
    expect(src).not.toMatch(/RK5/);
    expect(src).not.toMatch(/7980224/);
    expect(src).not.toMatch(/sfh-nhs-trust/);
    expect(src).not.toMatch(/sfh-gynae-2ww/);
  });

  it("useFormSchemaTeach preloads via loadTaughtLibrarySchema", () => {
    const src = fs.readFileSync(path.join(OPS, "useFormSchemaTeach.ts"), "utf8");
    expect(src).toMatch(/loadTaughtLibrarySchema/);
    expect(src).toMatch(/organizationId/);
    expect(src).toMatch(/serviceId/);
  });

  it("review dialog passes payload organization_id and service_id into teach", () => {
    const src = fs.readFileSync(
      path.join(OPS, "ExtractionQualityReviewDialog.tsx"),
      "utf8",
    );
    expect(src).toMatch(/raw\.organization_id/);
    expect(src).toMatch(/raw\.service_id/);
    expect(src).toMatch(/initialOrganizationId=\{data\?\.organization_id/);
    expect(src).toMatch(/initialServiceId=\{data\?\.service_id/);
  });
});
