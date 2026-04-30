import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("AuditSnapshotView scorecards", () => {
  const src = readFile("services/ui/src/components/audit/AuditSnapshotView.tsx");

  it("keeps missing years in the scorecard trend data", () => {
    expect(src).toContain("rawChartPoints.push({ label: String(yp.year), v: getYearValue(yp, metric.id) });");
    expect(src).toContain("Keep null years so the x-axis still shows all four years");
  });

  it("breaks the scorecard line when a year has no data", () => {
    expect(src).toContain("<LineChart data={chartPoints}");
    expect(src).toContain("connectNulls={false}");
    expect(src).toContain("interval={0}");
  });

  it("shows a per-year value and trend marker strip", () => {
    expect(src).toContain("gridTemplateColumns: `repeat(${chartPoints.length}, minmax(0, 1fr))`");
    expect(src).toContain("pointTrendLabel(point, index)");
    expect(src).toContain("No data");
  });

  it("uses the screening-excluded fast-track rate", () => {
    expect(src).toContain("label: \"Fast Track Referrals\"");
    expect(src).toContain("confirmed_cancers_via_2ww_excluding_screening_pct");
    expect(src).not.toContain("live: twwPct ?? twwRefRow?.pct ?? null");
  });

  it("gives users a plain-English calculation explanation", () => {
    expect(src).toContain("How we calculated this");
    expect(src).toContain("How?");
    expect(src).toContain("metricCalculationText");
    expect(src).toContain("We leave out cancers first found through the screening programme.");
  });

  it("uses GP-confirmed avoidable delay as the 2019 comparator for potential delays", () => {
    expect(src).toContain("baseline: resolveBenchmarkValue(bm, \"avoidable_delays.avoidable_delay_pct\", orgSelected)");
    expect(src).toContain("2019 is GP-confirmed. Later years are potential delay signals.");
    expect(src).toContain("The 2019 value is different. It is a GP-confirmed avoidable delay measure.");
  });

  it("does not plot denominator-free zeroes for safety netting or potential delays", () => {
    const pageSrc = readFile("services/ui/src/app/audit/page.tsx");
    expect(pageSrc).toContain("snData != null && snData.total_episodes > 0");
    expect(pageSrc).toContain("coData != null && coData.total_episodes > 0");
  });

  it("uses the scorecards as the trend view and skips the old trend table", () => {
    expect(src).toContain("What do I need to know?");
    expect(src).toContain("What do I need to do about it?");
    expect(src).not.toContain("function TrendTable");
    expect(src).not.toContain("How is the trend moving?");
  });

  it("does not render the old expandable summary table", () => {
    expect(src).not.toContain("SummaryCard");
    expect(src).not.toContain("Show full audit summary");
    expect(src).not.toContain("Collapse in=");
  });

  it("uses scorecard-shaped loading skeletons", () => {
    expect(src).toContain("function ScorecardSkeleton");
    expect(src).toContain("<ScorecardSkeleton />");
    expect(src).not.toContain("AuditChartSkeleton variant=\"area\"");
    expect(src).not.toContain("Loading audit trend table");
  });
});
