/**
 * VT-2E8544FD -- Place of Presentation audit section chrome.
 *
 * Static-source verification:
 *   - The section renders 2018 plus three live calendar-year pie cards.
 *   - The live cards fetch /analytics/audit/place-of-presentation by Jan-Dec year.
 *   - The nested pie treatment keeps GP surgery and non-GP visible in the outer ring.
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
    expect(section).toMatch(/const\s+BASELINE_YEAR\s*=\s*2018/);
    expect(section).toMatch(/currentYear\s*-\s*2/);
    expect(section).toMatch(/currentYear\s*-\s*1/);
    expect(section).toMatch(/\[currentYear\s*-\s*2,\s*currentYear\s*-\s*1,\s*currentYear\]/);
    expect(section).toMatch(/yearLabel=\{String\(BASELINE_YEAR\)\}/);
    expect(section).toMatch(/yearLabel=\{String\(state\.year\)\}/);
  });

  test("fetches live place data for Jan-Dec calendar windows scoped to the selected org", () => {
    expect(section).toMatch(/fetchAuditPlaceOfPresentation/);
    expect(section).toMatch(/calendarYearWindow/);
    expect(section).toMatch(/from:\s*`\$\{year\}-01-01`/);
    expect(section).toMatch(/to:\s*`\$\{year\}-12-31`/);
    expect(section).toMatch(/orgId,\s*window\.from,\s*window\.to/);
    expect(page).toMatch(/<PlaceOfPresentationSection[\s\S]*?orgId=\{orgId \?\? undefined\}/);
  });

  test("uses nested pie charts with GP surgery green and non-GP red outer ring", () => {
    expect(section).toMatch(/PieChart/);
    expect(section).toMatch(/<Pie[\s\S]*?outerRadius=\{58\}/);
    expect(section).toMatch(/<Pie[\s\S]*?innerRadius=\{68\}[\s\S]*?outerRadius=\{86\}/);
    expect(section).toMatch(/const\s+GP_GREEN\s*=\s*"#16A34A"/);
    expect(section).toMatch(/const\s+NON_GP_RED\s*=\s*"#DC2626"/);
    expect(section).toMatch(/Outer ring: GP Surgery/);
    expect(section).toMatch(/Outer ring: Non-GP/);
    expect(section).not.toMatch(/ComparisonBarChart/);
  });

  test("derives the 2018 baseline from place-of-presentation benchmark metrics", () => {
    expect(section).toMatch(/buildBaselineRows/);
    expect(section).toMatch(/place_of_presentation\.gp_surgery_pct/);
    expect(section).toMatch(/place_of_presentation\.ae_pct/);
  });
});
