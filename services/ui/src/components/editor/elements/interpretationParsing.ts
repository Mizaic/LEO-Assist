import { InterpretationElement as InterpretationElementType } from '@/lib/types/layout';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ParsedPreview {
  summary: string;
  insights: Array<string | Record<string, unknown>>;
  quality_checks: Array<string | Record<string, unknown>>;
  recommended_measures: Array<string | Record<string, unknown>>;
  follow_up_questions: Array<string | Record<string, unknown>>;
  caveats: Array<string | Record<string, unknown>>;
}

const EMPTY_PREVIEW: ParsedPreview = {
  summary: '',
  insights: [],
  quality_checks: [],
  recommended_measures: [],
  follow_up_questions: [],
  caveats: [],
};

/* ------------------------------------------------------------------ */
/*  JSON extraction helpers                                            */
/* ------------------------------------------------------------------ */

export function extractJsonFromFence(text: string): string | null {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  return match ? match[1].trim() : null;
}

export function extractSummaryField(text: string): string | null {
  const match = text.match(/"summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"/);
  if (!match) return null;
  try {
    return JSON.parse(`"${match[1]}"`);
  } catch {
    return match[1];
  }
}

export function extractFirstJsonObject(text: string): string | null {
  const start = text.indexOf('{');
  if (start === -1) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = start; i < text.length; i++) {
    const char = text[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === '{') {
      depth++;
    } else if (char === '}') {
      depth--;
      if (depth === 0) {
        return text.slice(start, i + 1);
      }
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  Parse preview                                                      */
/* ------------------------------------------------------------------ */

function tryParseJsonPreview(jsonStr: string): ParsedPreview | null {
  try {
    const parsed = JSON.parse(jsonStr);
    return {
      summary: typeof parsed.summary === 'string' ? parsed.summary : '',
      insights: Array.isArray(parsed.insights) ? parsed.insights : [],
      quality_checks: Array.isArray(parsed.quality_checks) ? parsed.quality_checks : [],
      recommended_measures: Array.isArray(parsed.recommended_measures) ? parsed.recommended_measures : [],
      follow_up_questions: Array.isArray(parsed.follow_up_questions) ? parsed.follow_up_questions : [],
      caveats: Array.isArray(parsed.caveats) ? parsed.caveats : [],
    };
  } catch {
    return null;
  }
}

function parseEmbeddedJson(summaryStr: string): ParsedPreview | null {
  const jsonStr = extractJsonFromFence(summaryStr) ?? extractFirstJsonObject(summaryStr);
  if (jsonStr) {
    const result = tryParseJsonPreview(jsonStr);
    if (result) return result;
  }

  const summaryField = extractSummaryField(summaryStr);
  if (summaryField) {
    return { ...EMPTY_PREVIEW, summary: summaryField };
  }
  return null;
}

export function parsePreview(preview: InterpretationElementType['preview']): ParsedPreview {
  if (!preview) return { ...EMPTY_PREVIEW };

  const summaryStr = typeof preview.summary === 'string' ? preview.summary : '';
  const hasEmbeddedJson =
    summaryStr.includes('```') ||
    (summaryStr.trim().startsWith('{') && summaryStr.includes('"summary"'));

  if (hasEmbeddedJson) {
    const result = parseEmbeddedJson(summaryStr);
    if (result) return result;
  }

  return {
    summary: summaryStr,
    insights: preview.insights || [],
    quality_checks: preview.quality_checks || [],
    recommended_measures: preview.recommended_measures || [],
    follow_up_questions: preview.follow_up_questions || [],
    caveats: preview.caveats || [],
  };
}

/* ------------------------------------------------------------------ */
/*  Display formatters                                                 */
/* ------------------------------------------------------------------ */

export function formatValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

function formatObjectParts(record: Record<string, unknown>, fields: string[]): string {
  const parts = fields
    .map((field) => (record[field] ? `${capitalize(field)}: ${formatValue(record[field])}` : ''))
    .filter(Boolean);
  return parts.join(' • ') || formatValue(record);
}

function capitalize(s: string): string {
  return s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export function formatInsight(item: unknown): string {
  if (item && typeof item === 'object' && !Array.isArray(item)) {
    return formatObjectParts(item as Record<string, unknown>, ['theme', 'observation', 'clinical_relevance']);
  }
  return formatValue(item);
}

export function formatQualityCheck(item: unknown): string {
  if (item && typeof item === 'object' && !Array.isArray(item)) {
    return formatObjectParts(item as Record<string, unknown>, ['check', 'status', 'detail']);
  }
  return formatValue(item);
}

export function formatRecommendation(item: unknown): string {
  if (item && typeof item === 'object' && !Array.isArray(item)) {
    return formatObjectParts(item as Record<string, unknown>, ['measure', 'rationale', 'priority']);
  }
  return formatValue(item);
}
