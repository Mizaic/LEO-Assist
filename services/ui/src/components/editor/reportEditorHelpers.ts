import type {
  ElementType,
  LayoutPage,
  MeasureElement,
  TableElement,
  ChartElement,
} from '@/lib/types/layout';

// ── Shared types ─────────────────────────────────────────────────────────────

export interface PendingDrop {
  pageId: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

// ── Default element sizes (mm) ───────────────────────────────────────────────

export const DEFAULT_ELEMENT_SIZES: Record<ElementType, { w: number; h: number }> = {
  measure: { w: 80, h: 40 },
  interpretation: { w: 120, h: 60 },
  executiveSummary: { w: 140, h: 70 },
  text: { w: 60, h: 20 },
  heading1: { w: 120, h: 20 },
  heading2: { w: 110, h: 18 },
  heading3: { w: 100, h: 16 },
  subtitle: { w: 100, h: 16 },
  bulletList: { w: 80, h: 40 },
  checklist: { w: 80, h: 40 },
  divider: { w: 120, h: 6 },
  cover: { w: 180, h: 120 },
  image: { w: 60, h: 60 },
  table: { w: 100, h: 60 },
  chart: { w: 100, h: 80 },
  kpiCard: { w: 60, h: 40 },
  heroStats: { w: 120, h: 60 },
  comparisonBars: { w: 100, h: 60 },
  populationPyramid: { w: 100, h: 80 },
  tableOfContents: { w: 120, h: 80 },
  pathwayGantt: { w: 140, h: 80 },
  complianceHeatmap: { w: 140, h: 80 },
  cssMatchProgression: { w: 140, h: 60 },
};

// ── Formatters ───────────────────────────────────────────────────────────────

export function formatValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

function formatObjectParts(record: Record<string, unknown>, keys: string[]): string {
  return keys
    .map((key) => {
      const label = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
      return record[key] ? `${label}: ${formatValue(record[key])}` : '';
    })
    .filter(Boolean)
    .join(' • ');
}

function formatRecord(item: unknown, keys: string[]): string {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    return formatValue(item);
  }
  const record = item as Record<string, unknown>;
  return formatObjectParts(record, keys) || formatValue(item);
}

export function formatInsight(item: unknown): string {
  return formatRecord(item, ['theme', 'observation', 'clinical_relevance']);
}

export function formatQualityCheck(item: unknown): string {
  return formatRecord(item, ['check', 'status', 'detail']);
}

export function formatRecommendation(item: unknown): string {
  return formatRecord(item, ['measure', 'rationale', 'priority']);
}

// ── Measure ID collection ────────────────────────────────────────────────────

export function collectMeasureIds(pages: LayoutPage[]): string[] {
  const ids = new Set<string>();
  pages.forEach((page) => {
    page.elements.forEach((element) => {
      if (element.type === 'measure') {
        const measureId = (element as MeasureElement).measureId;
        if (measureId) ids.add(measureId);
      }
      if (element.type === 'table' || element.type === 'chart') {
        const dataSource = (element as TableElement | ChartElement).dataSource;
        if (dataSource) ids.add(dataSource);
      }
    });
  });
  return Array.from(ids);
}
