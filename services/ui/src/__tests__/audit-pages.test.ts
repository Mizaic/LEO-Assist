/**
 * VT-AUDIT-PAGES -- multi-page audit report helpers (live unit layer)
 *
 * Atlas trace:
 *   DI: DI-AUDIT-PAGES
 *   DO: DO-A9863AB6
 *
 * Verifies the back-compatible page model: templates with no pages render as a
 * single implicit page, and tiles with no page_id fall on the first page.
 */

import {
  DEFAULT_PAGE_ID,
  resolvePages,
  tilesForPage,
} from "@/lib/auditPages";
import type { AuditTile } from "@/lib/auditTemplateApi";

const tile = (id: string, page?: string): AuditTile => ({
  tile_id: id,
  label: id,
  tile_type: "bar_chart",
  metric_id: `m-${id}`,
  param_overrides: {},
  page_id: page,
  layout: { x: 0, y: 0, w: 4, h: 3 },
});

describe("audit page helpers", () => {
  test("resolvePages synthesises a single default page when none exist", () => {
    expect(resolvePages(undefined)).toEqual([
      { page_id: DEFAULT_PAGE_ID, title: "Page 1" },
    ]);
    expect(resolvePages([])).toHaveLength(1);
  });

  test("resolvePages returns explicit pages unchanged", () => {
    const pages = [
      { page_id: "a", title: "Overview" },
      { page_id: "b", title: "Detail" },
    ];
    expect(resolvePages(pages)).toBe(pages);
  });

  test("tiles with no page_id fall on the first page (back-compat)", () => {
    const tiles = [tile("t1"), tile("t2", "b")];
    const onFirst = tilesForPage(tiles, "a", true);
    expect(onFirst.map((t) => t.tile_id)).toEqual(["t1"]);
  });

  test("tiles are filtered to their explicit page", () => {
    const tiles = [tile("t1", "a"), tile("t2", "b"), tile("t3", "b")];
    const onB = tilesForPage(tiles, "b", false);
    expect(onB.map((t) => t.tile_id)).toEqual(["t2", "t3"]);
  });

  test("a non-first page does not absorb page_id-less tiles", () => {
    const tiles = [tile("t1"), tile("t2", "b")];
    const onB = tilesForPage(tiles, "b", false);
    expect(onB.map((t) => t.tile_id)).toEqual(["t2"]);
  });
});
