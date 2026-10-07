/**
 * Read the form recognition evidence stored on a paused extraction task.
 *
 * Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5
 */

export interface RecognitionScore {
  form_name: string;
  matched: string[];
  missing: string[];
}

export interface RecognitionRow {
  outcome: string;
  title: string;
  best: RecognitionScore | null;
}

const MAX_MISSING_SHOWN = 5;

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item ?? "")).filter(Boolean) : [];
}

function toScore(value: unknown): RecognitionScore | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  return {
    form_name: String(raw.form_name || raw.fingerprint || ""),
    matched: strings(raw.matched),
    missing: strings(raw.missing),
  };
}

export function toRecognitionRows(value: unknown): RecognitionRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row) => ({
      outcome: String(row.outcome ?? ""),
      title: String(row.title ?? ""),
      best: toScore(row.best),
    }));
}

export function closestFormLine(best: RecognitionScore): string {
  const total = best.matched.length + best.missing.length;
  return `Closest taught form: ${best.form_name}. We found ${best.matched.length} of its ${total} headings.`;
}

export function missingHeadingsLine(missing: string[]): string {
  if (!missing.length) return "";
  const shown = missing.slice(0, MAX_MISSING_SHOWN).join(", ");
  const extra = missing.length - MAX_MISSING_SHOWN;
  return `Headings we could not find: ${shown}${extra > 0 ? `, and ${extra} more` : ""}.`;
}
