import type { LayoutJson, LayoutElement } from '@/lib/types/layout';

export interface TocEntry {
  elementId: string;
  pageIndex: number;
  label: string;
  level: 1 | 2 | 3;
}

const TOC_EXTRACTORS: Partial<
  Record<string, (el: LayoutElement) => { label: string; level: 1 | 2 | 3 } | null>
> = {
  cover: (el) => ({
    label: (el as any).title || 'Cover',
    level: 1,
  }),
  heading1: (el) => ({
    label: (el as any).text,
    level: 1,
  }),
  heading2: (el) => ({
    label: (el as any).text,
    level: 2,
  }),
  heading3: (el) => ({
    label: (el as any).text,
    level: 3,
  }),
  executiveSummary: (el) => ({
    label: (el as any).title || 'Executive Summary',
    level: 1,
  }),
};

/**
 * Scan a layout and build a flat, ordered list of TOC entries.
 *
 * Entries are ordered by page, then top-to-bottom (y), then left-to-right (x).
 * Elements without a recognisable title are skipped.
 */
export function buildTocEntries(
  layout: LayoutJson,
  excludeElementId?: string,
): TocEntry[] {
  const entries: TocEntry[] = [];

  layout.pages.forEach((page, pageIndex) => {
    const sorted = [...page.elements].sort(
      (a, b) => a.y - b.y || a.x - b.x,
    );

    for (const el of sorted) {
      if (el.id === excludeElementId) continue;

      const extractor = TOC_EXTRACTORS[el.type];
      if (!extractor) continue;

      const result = extractor(el);
      if (result && result.label?.trim()) {
        entries.push({
          elementId: el.id,
          pageIndex,
          label: result.label,
          level: result.level,
        });
      }
    }
  });

  return entries;
}
