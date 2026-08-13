/**
 * Presence helpers for Validation Lab inspector state-key chips.
 *
 * Atlas trace:
 *   UN: UN-4DCE95C8
 *   DI: DI-FE423B8D
 *   DO: DO-158BE606
 *   VT: VT-C9851641
 */

import { entityEvidence, formatEvidenceTooltip } from "./stageWorkItems";

/** High enough that a stage dump stays readable. Remainder note if bigger. */
export const TOOLTIP_MAX = 80_000;

export function isPresentValue(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "number" || typeof value === "boolean") return true;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

export function formatKeyTooltip(
  value: unknown,
  ready: boolean,
  sentences: unknown[] = [],
): string {
  if (!ready) return "Value not loaded yet";
  if (!isPresentValue(value)) return "No value";
  if (Array.isArray(value) && value.length && looksLikeEntities(value)) {
    return clip(formatEntityLines(value, sentences), TOOLTIP_MAX);
  }
  if (typeof value === "string") return clip(value, TOOLTIP_MAX);
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return clip(JSON.stringify(value, null, 2) ?? "null", TOOLTIP_MAX);
  } catch {
    return "[unserializable]";
  }
}

function looksLikeEntities(value: unknown[]): boolean {
  const first = value.find((row) => row && typeof row === "object");
  if (!first || typeof first !== "object") return false;
  const row = first as Record<string, unknown>;
  return Boolean(row.text || row.entity_text || row.concept_id || row.coding);
}

function formatEntityLines(value: unknown[], sentences: unknown[]): string {
  const blocks: string[] = [];
  for (const row of value) {
    if (!row || typeof row !== "object") continue;
    const ev = entityEvidence(row as Record<string, unknown>, sentences);
    if (!ev.text && !ev.code) continue;
    blocks.push(formatEvidenceTooltip(ev));
  }
  return blocks.join("\n\n") || JSON.stringify(value);
}

function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  const extra = text.length - max;
  return `${text.slice(0, max)}\n\n... truncated, ${extra} more characters`;
}
