/**
 * Static-source VT: domains redesign -- coverage stats inline + validation lab deep-link.
 * P2-I.
 */
import * as fs from "fs";
import * as path from "path";

const DOMAIN_CARD = path.join(
  __dirname,
  "../app/settings/domains/_components/DomainCard.tsx",
);
const ANALYTICS_API = path.join(__dirname, "../lib/analyticsApi.ts");

describe("DomainSummary type -- coverage_pct field", () => {
  let src: string;
  beforeAll(() => { src = fs.readFileSync(ANALYTICS_API, "utf-8"); });

  it("DomainSummary has optional coverage_pct", () => {
    expect(src).toMatch(/coverage_pct\?.*number/);
  });

  it("DomainSummary has optional coded_encounter_count", () => {
    expect(src).toMatch(/coded_encounter_count\?.*number/);
  });
});

describe("DomainCard -- inline coverage stats", () => {
  let src: string;
  beforeAll(() => { src = fs.readFileSync(DOMAIN_CARD, "utf-8"); });

  it("renders coverage_pct when present", () => {
    expect(src).toMatch(/coverage_pct/);
  });

  it("has a Test in lab / validation-lab deep-link", () => {
    expect(src).toMatch(/validation-lab|onTestInLab|testInLab/i);
  });

  it("shows a progress bar or linear progress for coverage", () => {
    expect(src).toMatch(/LinearProgress|coverage.*bar|progress.*coverage|CoverageBar/i);
  });
});
