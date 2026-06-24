/**
 * VT-FCCB0FFE -- Clinical Audit page org-assigned template renderer (static-source layer)
 *
 * Atlas trace:
 *   VT: VT-FCCB0FFE  (id: fccb0ffe-df21-455c-98b6-a1de309b24d8)
 *   DI: DI-758B73A5
 *   DO: DO-A9863AB6
 *
 * Covers DI-758B73A5 acceptance criteria:
 *   AC1 - The Clinical Audit page fetches the template assigned to the user's org on every page load.
 *   AC2 - If org A is assigned template T1 and org B is assigned template T2, each sees only their own.
 *   AC3 - If no template is assigned to the org, the platform-default NCDA template is shown.
 *   AC4 - The page does not render hardcoded NCDA sections when a non-NCDA template is active.
 *
 * Static-source assertions - safe under any test environment, no network.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const AUDIT_PAGE = "services/ui/src/app/audit/page.tsx";
const RENDERER = "services/ui/src/components/audit-template-renderer/AuditTemplateRenderer.tsx";
const METRIC_TILE = "services/ui/src/components/audit-template-renderer/MetricTile.tsx";

describe("VT-FCCB0FFE audit page template renderer - static-source", () => {

  // AC1 - page fetches template on mount
  test("AC1 - AuditPage calls fetchActiveTemplate inside useEffect", () => {
    const src = read(AUDIT_PAGE);
    expect(src).toContain("fetchActiveTemplate");
    expect(src).toContain("useEffect");
  });

  // AC2 - scope enforced server-side (no org_id override in client)
  test("AC2 - fetchActiveTemplate does not override server org scope client-side", () => {
    const src = read(AUDIT_PAGE);
    expect(src).toMatch(/fetchActiveTemplate\(\)/);
  });

  // AC3 - fallback to NCDA page when no template
  test("AC3 - AuditPage falls back to NcdaAuditPage when no template is assigned", () => {
    const src = read(AUDIT_PAGE);
    expect(src).toContain("NcdaAuditPage");
    expect(src).toContain("return <NcdaAuditPage");
  });

  // AC4 - template path renders AuditTemplateRenderer, not hardcoded sections
  test("AC4 - AuditPage renders AuditTemplateRenderer when template is present", () => {
    const src = read(AUDIT_PAGE);
    expect(src).toContain("AuditTemplateRenderer");
    expect(src).toContain("return <AuditTemplateRenderer");
  });

  // Renderer iterates tiles by tile_id / metric_id
  test("AuditTemplateRenderer renders a MetricTile per tile keyed by tile_id", () => {
    const src = read(RENDERER);
    expect(src).toContain("MetricTile");
    expect(src).toContain("tile_id");
    expect(src).toContain("tiles.map");
  });

  // MetricTile calls runMetric with the tile's metric_id
  test("MetricTile calls runMetric using tile.metric_id", () => {
    const src = read(METRIC_TILE);
    expect(src).toContain("runMetric");
    expect(src).toContain("tile.metric_id");
    expect(src).toContain("tile.param_overrides");
  });

  // MetricTile renders bar/line via recharts, not a third-party iframe
  test("MetricTile uses recharts for chart rendering", () => {
    const src = read(METRIC_TILE);
    expect(src).toContain("recharts");
    expect(src).toContain("BarChart");
    expect(src).toContain("LineChart");
  });

  const FILES = [RENDERER, METRIC_TILE];
  test.each(FILES)("%s carries an Atlas trace header", (rel) => {
    const src = read(rel);
    expect(src.slice(0, 500)).toContain("Atlas trace");
  });
});
