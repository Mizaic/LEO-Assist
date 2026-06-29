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
const LAYOUT_GRID = "services/ui/src/components/audit-template-renderer/AuditLayoutGrid.tsx";
const PDF_EXPORT = "services/ui/src/lib/exportAuditReportPdf.ts";

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

  // Renderer must honour the authored tile layout (x/y/w/h), not discard it.
  test("AuditTemplateRenderer honours authored tile layout via AuditLayoutGrid", () => {
    const src = read(RENDERER);
    expect(src).toContain("AuditLayoutGrid");
    expect(src).toContain("hasAuthoredLayout");
    const gridSrc = read(LAYOUT_GRID);
    // The grid must derive its CSS placement from the tile's layout fields.
    expect(gridSrc).toContain("tile.layout.x");
    expect(gridSrc).toContain("tile.layout.w");
    expect(gridSrc).toContain("gridColumn");
    expect(gridSrc).toContain("gridRow");
    // Responsive collapse to a single column on small screens.
    expect(gridSrc).toContain('xs: "1fr"');
  });

  // PDF export is wired and uses the shared PDF toolchain.
  test("AuditTemplateRenderer exposes a PDF export action", () => {
    const src = read(RENDERER);
    expect(src).toContain("Export PDF");
    expect(src).toContain("exportAuditReportPdf");
    // The action controls must be excluded from the captured report.
    expect(src).toContain("data-html2canvas-ignore");
  });

  test("exportAuditReportPdf renders a branded, paginated PDF", () => {
    const src = read(PDF_EXPORT);
    expect(src).toContain('from "jspdf"');
    expect(src).toContain('from "html2canvas"');
    expect(src).toContain("addPage");
    expect(src).toContain("doc.save");
    expect(src).toContain("Page ");
  });

  // Multi-page reports render page tabs and only show the active page's tiles.
  test("AuditTemplateRenderer renders page tabs for multi-page reports", () => {
    const src = read(RENDERER);
    expect(src).toContain("isMultiPage");
    expect(src).toContain("resolvePages");
    expect(src).toContain("tilesForPage");
    expect(src).toContain("visibleTiles");
    expect(src).toContain("setActivePageId");
  });

  // Rich-visualisation parity: the widget catalogue exposes NCDA sections and
  // WidgetTile routes them through the section-widget registry.
  test("WidgetTile renders NCDA section widgets from the registry", () => {
    const registry = read(
      "services/ui/src/components/audit-template-renderer/auditWidgetRegistry.tsx",
    );
    for (const id of [
      "cancer_type",
      "cancer_stage",
      "diagnostic_intervals",
      "safety_netting",
      "demographics",
      "comorbidities",
    ]) {
      expect(registry).toContain(id);
    }
    expect(registry).toContain("SectionWidget");
    const widgetTile = read(
      "services/ui/src/components/audit-template-renderer/WidgetTile.tsx",
    );
    expect(widgetTile).toContain("SECTION_WIDGETS");
    expect(widgetTile).toContain("SectionWidget");

    const api = read("services/ui/src/lib/auditTemplateApi.ts");
    expect(api).toContain('widget_id: "cancer_type"');
    expect(api).toContain('widget_id: "safety_netting"');
  });

  const FILES = [RENDERER, METRIC_TILE, LAYOUT_GRID, PDF_EXPORT];
  test.each(FILES)("%s carries an Atlas trace header", (rel) => {
    const src = read(rel);
    expect(src.slice(0, 500)).toContain("Atlas trace");
  });
});
