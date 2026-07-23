/**
 * Block-aware PDF page planning for SBAR capture canvases.
 *
 * Prefers page breaks between [data-pdf-block] elements (chrome, stage
 * cards). Only slices inside a block when that block alone is taller
 * than one page.
 *
 * Atlas trace:
 *   DO: DO-598A4BB1
 *   DI: DI-15BC0C79
 *   Risks: R-7299F8D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-598A4BB1")
 */

export interface PdfBlock {
  topPx: number;
  bottomPx: number;
}

export interface PdfPageSlice {
  topPx: number;
  heightPx: number;
}

/** Measure capture blocks in canvas pixels (DOM px * scale). */
export function collectPdfBlocks(
  root: HTMLElement,
  scale: number,
): PdfBlock[] {
  const rootRect = root.getBoundingClientRect();
  const nodes = root.querySelectorAll<HTMLElement>("[data-pdf-block]");
  return Array.from(nodes).map((el) => {
    const rect = el.getBoundingClientRect();
    const topPx = (rect.top - rootRect.top) * scale;
    const heightPx = rect.height * scale;
    return { topPx, bottomPx: topPx + heightPx };
  });
}

function pushSlice(pages: PdfPageSlice[], topPx: number, bottomPx: number) {
  const heightPx = bottomPx - topPx;
  if (heightPx <= 0) return;
  pages.push({ topPx, heightPx });
}

function sliceTallBlock(
  pages: PdfPageSlice[],
  block: PdfBlock,
  pageHpx: number,
) {
  let cursor = block.topPx;
  while (cursor < block.bottomPx) {
    const bottom = Math.min(cursor + pageHpx, block.bottomPx);
    pushSlice(pages, cursor, bottom);
    cursor = bottom;
  }
}

/**
 * Pack measured blocks into page slices that fit within pageHpx.
 * pageTop for the first page is 0 so root padding is included.
 */
export function planPdfPageSlices(
  blocks: PdfBlock[],
  pageHpx: number,
  totalHeightPx: number,
): PdfPageSlice[] {
  if (pageHpx <= 0) {
    return [{ topPx: 0, heightPx: Math.max(1, totalHeightPx) }];
  }
  if (blocks.length === 0) {
    return fallbackEqualSlices(totalHeightPx, pageHpx);
  }

  const pages: PdfPageSlice[] = [];
  let pageTop = 0;
  let pageBottom = 0;
  let started = false;

  for (const block of blocks) {
    const blockH = block.bottomPx - block.topPx;
    if (blockH > pageHpx) {
      if (started && pageBottom > pageTop) {
        pushSlice(pages, pageTop, pageBottom);
      }
      sliceTallBlock(pages, block, pageHpx);
      pageTop = block.bottomPx;
      pageBottom = pageTop;
      started = false;
      continue;
    }

    if (!started) {
      // First page keeps top at 0 (root padding). Later pages start at the block.
      if (pages.length > 0) pageTop = block.topPx;
      pageBottom = block.bottomPx;
      started = true;
      continue;
    }

    if (block.bottomPx - pageTop <= pageHpx) {
      pageBottom = block.bottomPx;
      continue;
    }

    pushSlice(pages, pageTop, pageBottom);
    pageTop = block.topPx;
    pageBottom = block.bottomPx;
    started = true;
  }

  if (started && pageBottom > pageTop) {
    pushSlice(pages, pageTop, pageBottom);
  }

  return extendLastSlice(pages, totalHeightPx, pageHpx);
}

function fallbackEqualSlices(
  totalHeightPx: number,
  pageHpx: number,
): PdfPageSlice[] {
  const pages: PdfPageSlice[] = [];
  let cursor = 0;
  const total = Math.max(1, totalHeightPx);
  while (cursor < total) {
    const bottom = Math.min(cursor + pageHpx, total);
    pushSlice(pages, cursor, bottom);
    cursor = bottom;
  }
  return pages;
}

function extendLastSlice(
  pages: PdfPageSlice[],
  totalHeightPx: number,
  pageHpx: number,
): PdfPageSlice[] {
  if (pages.length === 0) {
    return fallbackEqualSlices(totalHeightPx, pageHpx);
  }
  const last = pages[pages.length - 1];
  const covered = last.topPx + last.heightPx;
  if (covered >= totalHeightPx) return pages;
  const trailing = totalHeightPx - covered;
  if (last.heightPx + trailing <= pageHpx) {
    last.heightPx += trailing;
    return pages;
  }
  pushSlice(pages, covered, totalHeightPx);
  return pages;
}
