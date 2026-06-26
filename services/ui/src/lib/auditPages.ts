/**
 * Page (tab) helpers for multi-page audit reports.
 *
 * A template with no `pages` is treated as a single implicit page so older
 * single-page templates keep working unchanged. Tiles with no `page_id`
 * belong to the first page.
 *
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-AUDIT-PAGES
 */
import type { AuditPage, AuditTile } from "./auditTemplateApi";

export const DEFAULT_PAGE_ID = "page-1";
export const DEFAULT_PAGE_TITLE = "Page 1";

/** Return the report's pages, synthesising a single default page if none. */
export function resolvePages(pages?: AuditPage[]): AuditPage[] {
  if (pages && pages.length > 0) return pages;
  return [{ page_id: DEFAULT_PAGE_ID, title: DEFAULT_PAGE_TITLE }];
}

/** Tiles that belong to a given page (tiles with no page_id fall on page 1). */
export function tilesForPage(
  tiles: AuditTile[],
  pageId: string,
  isFirstPage: boolean,
): AuditTile[] {
  return tiles.filter((t) => {
    const tilePage = t.page_id ?? DEFAULT_PAGE_ID;
    if (isFirstPage && tilePage === DEFAULT_PAGE_ID) return true;
    return tilePage === pageId;
  });
}
