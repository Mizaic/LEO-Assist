import * as fs from "fs";
import * as path from "path";

const root = path.resolve(__dirname, "../../../..");

function source(relativePath: string): string {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

describe("local guideline import chrome", () => {
  test("shows structure verification before import", () => {
    const file = source(
      "services/ui/src/app/admin/guidance/LocalGuidelineImportDialog.tsx",
    );

    expect(file).toContain("/api/guidance/local/structure");
    expect(file).toContain("Structure and verify");
    expect(file).toContain("likely_incorrect");
  });

  test("allows create blank without guideline text", () => {
    const file = source(
      "services/ui/src/app/admin/guidance/LocalGuidelineImportDialog.tsx",
    );

    expect(file).toContain("/api/guidance/local/create-blank");
    expect(file).toContain("Create blank");
    expect(file).toContain("Guideline text (optional)");
    // Blank create is gated on identity only; pasted text must not block it.
    expect(file).toMatch(/canCreateBlank\s*=\s*metaOk/);
    expect(file).toContain("X-Requested-With");
    expect(file).toContain("#loaded-guidelines");
  });

  test("selects the local subgraph endpoint", () => {
    const dialog = source(
      "services/ui/src/app/admin/guidance/RecommendationPickerDialog.tsx",
    );
    const api = source(
      "services/ui/src/app/admin/guidance/recommendationPickerApi.ts",
    );

    expect(api).toContain('"/api/guidance/local"');
    expect(api).toContain('source === "local_guideline"');
    expect(dialog).toContain("fetchSubgraph");
  });

  test("Build by hand posts create-blank and surfaces detail errors", () => {
    const dialog = source(
      "services/ui/src/app/admin/guidance/RecommendationPickerDialog.tsx",
    );
    const api = source(
      "services/ui/src/app/admin/guidance/recommendationPickerApi.ts",
    );

    expect(api).toContain("/api/guidance/rules/create-blank");
    expect(api).toContain("rec_id");
    expect(api).toContain("detail");
    expect(dialog).toContain("setEditError");
    expect(dialog).toContain("createBlankRule");
  });

  test("skips NICE check-update for local guidelines", () => {
    const file = source(
      "services/ui/src/app/admin/guidance/LoadedGuidelinesPanel.tsx",
    );

    expect(file).toContain('guideline_source !== "local_guideline"');
    expect(file).toContain("/api/nice/");
    expect(file).toContain("check-update");
  });

  test("exposes Link domain control for local guidelines", () => {
    const panel = source(
      "services/ui/src/app/admin/guidance/LoadedGuidelinesPanel.tsx",
    );
    const dialog = source(
      "services/ui/src/app/admin/guidance/LocalGuidelineLinkDomainDialog.tsx",
    );

    expect(panel).toContain("Link domain");
    expect(panel).toContain("LocalGuidelineLinkDomainDialog");
    expect(dialog).toContain("/api/guidance/local/");
    expect(dialog).toContain("link-domain");
    expect(dialog).toContain("/api/proxy/analytics/domains");
    expect(dialog).toContain("domain_id");
  });

  test("exposes Delete for local guidelines with clean API call", () => {
    const panel = source(
      "services/ui/src/app/admin/guidance/LoadedGuidelinesPanel.tsx",
    );

    expect(panel).toContain("Delete");
    expect(panel).toContain('method: "DELETE"');
    expect(panel).toContain("/api/guidance/local/");
    expect(panel).toContain("permanently removes");
  });
});
