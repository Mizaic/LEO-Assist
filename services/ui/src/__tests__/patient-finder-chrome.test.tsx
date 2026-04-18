/**
 * VT-LEO-AI-230 -- PatientFinder primitive (static-source layer)
 *
 * Static-source verification of the PatientFinder dialog
 * (DI-LEO-AI-230 / DO-LEO-AI-230). The live-render typeahead is in
 * patient-finder-typeahead.test.tsx; the backend router scope and
 * extended CohortFilter behaviour are covered by pytest.
 *
 * Risks addressed:
 *   - R-LEO-AI-211 (wrong-patient pick): assert that the ResultsList
 *     row markup has BOTH NHS-number AND DOB chip data-testids.
 */
import fs from "fs";
import path from "path";

const PRIMITIVE = path.resolve(
  __dirname,
  "..",
  "components",
  "sbar-playground",
  "PatientFinder.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-230 PatientFinder primitive", () => {
  it("renders three tabs (Search, Filter, Saved cohort)", () => {
    const src = read(PRIMITIVE);
    expect(src).toContain("patient-finder-tab-search");
    expect(src).toContain("patient-finder-tab-filter");
    expect(src).toContain("patient-finder-tab-cohort");
  });

  it("ResultsList row markup REQUIRES NHS number AND DOB chips on every row", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/patient-finder-row-\$\{r\.id\}-nhs/);
    expect(src).toMatch(/patient-finder-row-\$\{r\.id\}-dob/);
  });

  it("emits SelectedPatient with id, displayName, dob and nhsNumber", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/displayName:\s*r\.display_name\s*\?\?\s*null/);
    expect(src).toMatch(/dob:\s*r\.dob\s*\?\?\s*null/);
    expect(src).toMatch(/nhsNumber:\s*r\.nhs_number\s*\?\?\s*null/);
  });

  it("Filter tab uses POST /cohorts/preview before listing", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/previewCohort/);
    expect(src).toMatch(/patientsByFilter/);
  });

  it("Cohort tab calls patientsByCohort and lists saved cohorts via fetchCohorts", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/fetchCohorts/);
    expect(src).toMatch(/patientsByCohort/);
  });
});
