/**
 * VT-2E8544FD -- Place of Presentation audit section chrome.
 *
 * Static-source verification:
 *   - The section renders 2018 plus live calendar-year pie cards.
 *   - The live cards use the shared audit year-window loader.
 *   - The pie treatment keeps stable colours for known presentation places.
 *
 * Design Controls: DI-C65FD45B, DO-2E8544FD.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const SECTION_PATH =
  "services/ui/src/components/audit/PlaceOfPresentationSection.tsx";
const PAGE_PATH = "services/ui/src/app/audit/page.tsx";

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("VT-2E8544FD Place of Presentation audit section", () => {
  let section: string;
  let page: string;

  beforeAll(() => {
    section = read(SECTION_PATH);
    page = read(PAGE_PATH);
  });

  test("renders 2018 baseline plus year-before-last, last year, and current-year cards", () => {
    expect(section).toMatch(/BASELINE_YEAR/);
    expect(section).toMatch(/useAuditYearWindows/);
    expect(section).toMatch(/yearLabel=\{String\(BASELINE_YEAR\)\}/);
    expect(section).toMatch(/yearLabel=\{String\(state\.year\)\}/);
  });

  test("fetches live place data for Jan-Dec calendar windows scoped to the selected org", () => {
    expect(section).toMatch(/fetchAuditPlaceOfPresentation/);
    expect(section).toMatch(/useAuditYearWindows<AuditPlaceRow\[\]>/);
    expect(section).toMatch(/\{\s*orgId\s*\}/);
    expect(page).toMatch(/<PlaceOfPresentationSection/);
  });

  test("uses pie charts with stable colours for known places", () => {
    expect(section).toMatch(/PieChart/);
    expect(section).toMatch(/outerRadius=\{86\}/);
    expect(section).toMatch(/"gp surgery":\s*"#2563EB"/);
    expect(section).toMatch(/"a&e":\s*"#EA580C"/);
    expect(section).toMatch(/PLACE_COLOUR_MAP/);
    expect(section).not.toMatch(/ComparisonBarChart/);
  });

  test("derives the 2018 baseline from place-of-presentation benchmark metrics", () => {
    expect(section).toMatch(/buildBaselineRows/);
    expect(section).toMatch(/place_of_presentation\.gp_surgery_pct/);
    expect(section).toMatch(/place_of_presentation\.ae_pct/);
  });
});
