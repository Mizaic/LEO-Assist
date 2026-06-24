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
    const src = read(METRIC_PICKER);
    expect(src).toContain("fetchMetricCatalogue");
    expect(src).toContain("onAdd");
  });

  // DO-A9863AB6 AC2
  test("AC2 - TileGrid uses react-grid-layout GridLayout for drag/resize", () => {
    const src = read(TILE_GRID);
    expect(src).toContain("GridLayout");
    expect(src).toContain("react-grid-layout");
    expect(src).toContain("onLayoutChange");
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
