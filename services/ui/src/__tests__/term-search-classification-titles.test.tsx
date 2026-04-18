/**
 * Static-source VT for VT-LEO-AI-217 / VT-LEO-AI-218.
 *
 * Asserts that surfaces showing terminology results render the new
 * ICD-10 and OPCS-4 titles next to their codes (and that the OPCS-4
 * code itself is rendered, since it was not surfaced before).
 *
 * Static-source style is the canonical pattern for components that
 * issue network requests on mount (see ui-testing.mdc).
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const TERM_SEARCH = path.join(
  ROOT,
  "services/ui/src/components/TermSearch.tsx",
);
const SURFACE_FORMS = path.join(
  ROOT,
  "services/ui/src/app/settings/surface-forms/page.tsx",
);
const TYPES = path.join(ROOT, "services/ui/src/lib/types.ts");
const LEGACY = path.join(ROOT, "services/ui/src/lib/api/legacy.ts");

function read(p: string): string {
  return fs.readFileSync(p, "utf-8");
}

describe("VT-217/218: terminology result surfaces show classification titles", () => {
  describe("TermSearch result row", () => {
    const src = read(TERM_SEARCH);

    it("renders the ICD-10 title when present", () => {
      expect(src).toMatch(/r\.icd10_term/);
      expect(src).toMatch(/ICD-10:\s*\$\{r\.icd10\}/);
    });

    it("renders the OPCS-4 code and title when present", () => {
      expect(src).toMatch(/r\.opcs4/);
      expect(src).toMatch(/OPCS-4:\s*\$\{r\.opcs4\}/);
      expect(src).toMatch(/r\.opcs4_term/);
    });

    it("guards every title fragment behind a truthy check", () => {
      expect(src).toMatch(/r\.icd10_term \?/);
      expect(src).toMatch(/r\.opcs4_term \?/);
    });
  });

  describe("Surface forms grouped row", () => {
    const src = read(SURFACE_FORMS);

    it("renders the ICD-10 title when present", () => {
      expect(src).toMatch(/group\.icd10_term/);
      expect(src).toMatch(/ICD-10:\s*\$\{group\.icd10\}/);
    });

    it("renders the OPCS-4 code and title when present", () => {
      expect(src).toMatch(/group\.opcs4/);
      expect(src).toMatch(/OPCS-4:\s*\$\{group\.opcs4\}/);
      expect(src).toMatch(/group\.opcs4_term/);
    });
  });

  describe("Type contracts", () => {
    it("TermSearchResult declares icd10_term, opcs4 and opcs4_term", () => {
      const src = read(TYPES);
      expect(src).toMatch(/icd10_term\?:\s*string/);
      expect(src).toMatch(/opcs4\?:\s*string/);
      expect(src).toMatch(/opcs4_term\?:\s*string/);
    });

    it("ConceptGroup declares icd10_term, opcs4 and opcs4_term", () => {
      const src = read(LEGACY);
      expect(src).toMatch(/icd10_term\?:\s*string/);
      expect(src).toMatch(/opcs4\?:\s*string/);
      expect(src).toMatch(/opcs4_term\?:\s*string/);
    });
  });
});
