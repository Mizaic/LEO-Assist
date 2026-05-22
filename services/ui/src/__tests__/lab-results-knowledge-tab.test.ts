import { readFileSync } from "fs";
import { resolve } from "path";

const ROOT = resolve(__dirname, "../../../..");

function read(relPath: string): string {
  return readFileSync(resolve(ROOT, relPath), "utf8");
}

describe("Results/Labs Knowledge tab", () => {
  it("registers the tab and API proxy", () => {
    const knowledgePage = read("services/ui/src/app/admin/knowledge/page.tsx");
    const proxy = read("services/ui/src/proxy.ts");

    expect(knowledgePage).toMatch(/"results-labs"/);
    expect(knowledgePage).toMatch(/admin\/lab-results\/page/);
    expect(proxy).toMatch(/\/api\/lab-result-configs/);
  });

  it("contains editors for ranges, conversions, and interpretation SNOMED", () => {
    const panel = read(
      "services/ui/src/app/admin/lab-results/LabResultsPanel.tsx",
    );

    expect(panel).toMatch(/Reference range/);
    expect(panel).toMatch(/Unit conversion/);
    expect(panel).toMatch(/Interpretation SNOMED/);
    expect(panel).toMatch(/finding_concept_id/);
  });
});
