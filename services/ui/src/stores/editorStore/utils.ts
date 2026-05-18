/**
 * Utility constants and functions for the editor store.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import type { LayoutJson } from '@/lib/types/layout';
import { generateElementId, generatePageId } from '@/lib/types/layout';

export const MAX_HISTORY = 50;

export const GRID_SIZE = 5;

export function snapToGrid(value: number): number {
  return Math.round(value / GRID_SIZE) * GRID_SIZE;
}

export function normalizeLayout(
  layout: LayoutJson
): { layout: LayoutJson; didNormalize: boolean } {
  let didNormalize = false;
  const seenPageIds = new Set<string>();

  const pages = (layout.pages || []).map((page) => {
    let pageId = page.id || generatePageId();
    if (!page.id || seenPageIds.has(pageId)) {
      pageId = generatePageId();
      didNormalize = true;
    }
    seenPageIds.add(pageId);

    const seenElementIds = new Set<string>();
    const elements = (page.elements || []).map((element) => {
      let elementId = element.id || generateElementId(element.type);
      if (!element.id || seenElementIds.has(elementId)) {
        elementId = generateElementId(element.type);
        didNormalize = true;
      }
      seenElementIds.add(elementId);
      return { ...element, id: elementId };
    });

    if (elements.length !== (page.elements || []).length) {
      didNormalize = true;
    }

    return { ...page, id: pageId, elements };
  });

  return { layout: { ...layout, pages }, didNormalize };
}

export function pushHistory(
  past: LayoutJson[],
  future: LayoutJson[],
  layout: LayoutJson
): void {
  past.push(JSON.parse(JSON.stringify(layout)));
  if (past.length > MAX_HISTORY) past.shift();
  future.length = 0;
}
