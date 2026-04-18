/**
 * Static-source VT for VT-LEO-AI-301 (ICD-10) / VT-LEO-AI-302 (OPCS-4).
 *
 * Asserts that the terminology settings page renders cards and stat tiles
 * for the new ICD-10 and OPCS-4 packages, and that its layout contract
 * (2x2 grid) is preserved.
 *
 * Static-source style is the canonical pattern for pages that hit the
 * network on mount (see ui-testing.mdc).
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const PAGE = path.join(
  ROOT,
  "services/ui/src/app/settings/terminology/page.tsx",
);

function read(): string {
  return fs.readFileSync(PAGE, "utf-8");
}

describe("VT-217/218: terminology settings page chrome", () => {
  const src = read();

  it("declares package keys for snomed, dmd, icd10 and opcs4", () => {
    expect(src).toMatch(/PACKAGE_KEYS\s*=\s*\[\s*"snomed"\s*,\s*"dmd"\s*,\s*"icd10"\s*,\s*"opcs4"\s*\]/);
  });

  it("initialises selected packages to include icd10 and opcs4", () => {
    expect(src).toMatch(/new\s+Set\s*\(\s*\[\s*"snomed"\s*,\s*"dmd"\s*,\s*"icd10"\s*,\s*"opcs4"\s*\]/);
  });

  it("extends Neo4jCounts with icd10 and opcs4 fields", () => {
    expect(src).toMatch(/icd10_codes\?:\s*number/);
    expect(src).toMatch(/opcs4_codes\?:\s*number/);
    expect(src).toMatch(/opcs4_maps\?:\s*number/);
  });

  it("renders an ICD-10 codes stat tile", () => {
    expect(src).toMatch(/ICD-10 codes/);
    expect(src).toMatch(/neo4j\.icd10_codes/);
  });

  it("renders an OPCS-4 codes stat tile", () => {
    expect(src).toMatch(/OPCS-4 codes/);
    expect(src).toMatch(/neo4j\.opcs4_codes/);
  });

  it("renders an OPCS-4 maps stat tile", () => {
    expect(src).toMatch(/OPCS-4 maps/);
    expect(src).toMatch(/neo4j\.opcs4_maps/);
  });

  it("uses a 2x2 grid layout for the four package cards", () => {
    expect(src).toMatch(/gridTemplateColumns:\s*\{[^}]*sm:\s*"1fr 1fr"/);
  });

  it("does not list classification packages in a single horizontal Stack", () => {
    expect(src).not.toMatch(/<Stack[^>]*>\s*\{PACKAGE_KEYS\.map/);
  });
});
