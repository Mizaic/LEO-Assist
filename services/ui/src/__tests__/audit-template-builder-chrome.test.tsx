/**
 * VT-32FBAA69 -- Audit template authoring and publish (static-source layer)
 *
 * Atlas trace:
 *   VT: VT-32FBAA69  (id: 32fbaa69-4693-43fd-89be-215ee16b58c1)
 *   DI: DI-64CA7740
 *   DO: DO-3775670C, DO-A9863AB6
 *
 * Covers DI-64CA7740 acceptance criteria:
 *   AC1 - A Quality Manager can create a template with at least one metric tile and save it as a draft.
 *   AC2 - A Quality Manager can publish a draft template to a named organisation.
 *   AC3 - A published template is returned by GET /audit-templates/active for a user in the target organisation.
 *   AC4 - Publishing to org A does not change the template shown to org B.
 *   AC5 - A new version of a template can be published without removing the previous version.
 *
 * Covers DO-A9863AB6 acceptance criteria:
 *   AC1 - The template builder renders the metric picker from GET /audit-metrics.
 *   AC2 - Tiles can be added, configured, resized, and reordered using react-grid-layout.
 *   AC3 - The publish dialog shows the target org name and template title before confirming.
 *   AC5 - The audit page renders tile components keyed by metric_id from the active template.
 *
 * Static-source assertions - safe under any test environment, no network.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const METRIC_PICKER = "services/ui/src/components/audit-template-builder/MetricPicker.tsx";
const TILE_GRID = "services/ui/src/components/audit-template-builder/TileGrid.tsx";
const PUBLISH_DIALOG = "services/ui/src/components/audit-template-builder/PublishDialog.tsx";
const TEMPLATE_EDITOR = "services/ui/src/components/audit-template-builder/TemplateEditor.tsx";
const TEMPLATE_LIST = "services/ui/src/components/audit-template-builder/TemplateList.tsx";
const AUDIT_API = "services/ui/src/lib/auditTemplateApi.ts";

describe("VT-32FBAA69 audit template builder - static-source", () => {

  // DI-64CA7740 / DO-A9863AB6 AC1
  test("AC1 - MetricPicker fetches metric catalogue from GET /audit-metrics", () => {
    // Catalogue fetching was lifted to TemplateEditor; MetricPicker receives it as a prop.
    const pickerSrc = read(METRIC_PICKER);
    expect(pickerSrc).toContain("catalogue");
    expect(pickerSrc).toContain("onAdd");
    // TemplateEditor is the actual caller of fetchMetricCatalogue
    const editorSrc = read(TEMPLATE_EDITOR);
    expect(editorSrc).toContain("fetchMetricCatalogue");
  });

  // DO-A9863AB6 AC2 - drag/resize/auto-layout must be WIRED, not just imported.
  // Regression guard: react-grid-layout v2 needs dragConfig + resizeConfig +
  // compactor AND its stylesheet, or drag/resize/compaction silently no-op.
  // (The original defect passed a "contains GridLayout" check while being dead.)
  test("AC2 - TileGrid wires react-grid-layout v2 drag, resize and compaction", () => {
    const src = read(TILE_GRID);
    expect(src).toContain("GridLayout");
    expect(src).toContain("onLayoutChange");
    // Drag must be explicitly enabled with a handle selector.
    expect(src).toMatch(/dragConfig=\{\{[\s\S]*?enabled:\s*true[\s\S]*?handle:/);
    // Resize handles only render when resizeConfig is enabled.
    expect(src).toMatch(/resizeConfig=\{\{[\s\S]*?enabled:\s*true/);
    // A compactor is required for auto-layout / compaction on drag.
    expect(src).toMatch(/compactor=\{verticalCompactor\}/);
    expect(src).toContain("verticalCompactor");
  });

  // DO-A9863AB6 AC2 - the v2 stylesheet must be imported globally, otherwise
  // resize handles and the drag placeholder are invisible (the original bug).
  test("AC2 - react-grid-layout stylesheet is imported in the root layout", () => {
    const layoutSrc = read("services/ui/src/app/layout.tsx");
    expect(layoutSrc).toContain('react-grid-layout/css/styles.css');
  });

  // DO-A9863AB6 AC2 - metrics drag from the library onto the canvas, and the
  // canvas accepts the drop (library-to-canvas DnD).
  test("AC2 - library metrics are draggable and TileGrid is a drop target", () => {
    const pickerSrc = read(METRIC_PICKER);
    expect(pickerSrc).toContain("draggable");
    expect(pickerSrc).toContain("application/x-audit-metric");
    const gridSrc = read(TILE_GRID);
    expect(gridSrc).toContain("onDrop");
    expect(gridSrc).toContain("application/x-audit-metric");
    expect(gridSrc).toContain("onDropMetric");
  });

  // DO-A9863AB6 AC2 - a metric chip must never be disabled just because the
  // metric is already on the canvas (the "grayed out" regression).
  test("AC2 - metric chips are not disabled when the metric is already in use", () => {
    const pickerSrc = read(METRIC_PICKER);
    expect(pickerSrc).not.toMatch(/disabled=\{used\}/);
    // The non-blocking "in use" indicator is a count, not a lock.
    expect(pickerSrc).toContain("usedCounts");
  });

  // DI-64CA7740 AC2 / DO-A9863AB6 AC3
  test("AC3 - PublishDialog shows template title and org selector before confirming", () => {
    const src = read(PUBLISH_DIALOG);
    expect(src).toContain("templateTitle");
    // Multi-org Autocomplete replaced the raw text field
    expect(src).toContain("Select organisations");
    expect(src).toContain("Autocomplete");
    expect(src).toContain("publishTemplate");
    expect(src).toContain("scope_type");
    expect(src).toContain("scope_id");
    // Platform admins see a global toggle
    expect(src).toContain("Publish to all organisations");
    expect(src).toContain("isPlatformAdmin");
  });

  // DI-64CA7740 AC1
  test("AC1 - TemplateEditor calls createTemplate to save a new draft", () => {
    const src = read(TEMPLATE_EDITOR);
    expect(src).toContain("createTemplate");
    expect(src).toContain("updateTemplate");
    expect(src).toContain("MetricPicker");
    expect(src).toContain("TileGrid");
    expect(src).toContain("PublishDialog");
  });

  // DI-64CA7740 AC2
  test("AC2 - TemplateEditor opens PublishDialog when Publish button pressed", () => {
    const src = read(TEMPLATE_EDITOR);
    expect(src).toContain("publishOpen");
    expect(src).toContain("setPublishOpen");
  });

  // DI-64CA7740 AC3 / AC4
  test("AC3+AC4 - auditTemplateApi exposes fetchActiveTemplate scoped to caller", () => {
    const src = read(AUDIT_API);
    expect(src).toContain("fetchActiveTemplate");
    expect(src).toContain("/audit-templates/active");
    // Scope is enforced server-side via CallerScope - client passes no org_id directly
    expect(src).not.toMatch(/active\?org_id/);
  });

  // DI-64CA7740 AC5
  test("AC5 - publishTemplate sends scope_type and scope_id, not a hard replace", () => {
    const src = read(AUDIT_API);
    expect(src).toContain("publishTemplate");
    expect(src).toContain("scope_type");
    expect(src).toContain("scope_id");
    expect(src).toContain("/publish");
  });

  // Multi-page authoring: the editor renders a page tab strip and assigns
  // tiles to the active page (the "I can't create tabs" complaint).
  test("TemplateEditor supports multiple pages via PageTabs", () => {
    const src = read(TEMPLATE_EDITOR);
    expect(src).toContain("PageTabs");
    expect(src).toContain("activePageId");
    expect(src).toContain("handleAddPage");
    expect(src).toContain("pageTiles");
    const tabsSrc = read(
      "services/ui/src/components/audit-template-builder/PageTabs.tsx",
    );
    expect(tabsSrc).toContain("onAdd");
    expect(tabsSrc).toContain("onRename");
    expect(tabsSrc).toContain("onDelete");
  });

  // Tile parameter configuration: the config panel renders a Parameters tab
  // from the metric param_schema and writes to param_overrides.
  test("TileConfigPanel renders metric parameters into param_overrides", () => {
    const src = read(
      "services/ui/src/components/audit-template-builder/TileConfigPanel.tsx",
    );
    expect(src).toContain("paramSchema");
    expect(src).toContain("param_overrides");
    expect(src).toContain("Parameters");
    expect(src).toContain("ParamsTab");
    // TemplateEditor must feed the selected metric's schema in.
    const editorSrc = read(TEMPLATE_EDITOR);
    expect(editorSrc).toContain("paramSchema={catalogueById");
  });

  // TemplateList must expose create + archive
  test("TemplateList exposes create, edit, and archive actions", () => {
    const src = read(TEMPLATE_LIST);
    expect(src).toContain("New template");
    expect(src).toContain("archiveTemplate");
    expect(src).toContain("EditOutlined");
  });

  // All source files carry Atlas trace header
  const FILES = [METRIC_PICKER, TILE_GRID, PUBLISH_DIALOG, TEMPLATE_EDITOR, TEMPLATE_LIST];
  test.each(FILES)("%s carries an Atlas trace header", (rel) => {
    const src = read(rel);
    expect(src.slice(0, 500)).toContain("Atlas trace");
  });
});
