/**
 * Display helpers for Validation Lab test-patient cards.
 *
 * Atlas: DI-EB716E68 / DI-12D40786
 */

import type { LabCase } from "./labApi";

/** Compare strings so embedded numbers sort 1,2,10 not 1,10,2. */
export function naturalCompare(a: string, b: string): number {
  return String(a || "").localeCompare(String(b || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function caseSummary(c: LabCase): string {
  const summary = String(c.summary || "").trim();
  if (summary) return summary;
  const preview = String(c.referral_preview || "").trim();
  if (preview) return preview;
  return "";
}

export function caseTags(c: LabCase): string[] {
  const tags = Array.isArray(c.tags)
    ? c.tags.map((t) => String(t || "").trim()).filter(Boolean)
    : [];
  return tags.slice(0, 8);
}

export function caseSearchHaystack(c: LabCase): string {
  const parts = [
    c.title,
    c.id,
    c.patient_id,
    caseSummary(c),
    caseTags(c).join(" "),
    c.case_type,
    c.scenario_type,
  ];
  return parts.filter(Boolean).join(" ").toLowerCase();
}

export function sortCasesNaturally(cases: LabCase[]): LabCase[] {
  return [...cases].sort((a, b) =>
    naturalCompare(a.title || a.id, b.title || b.id),
  );
}

export function collectTagUniverse(cases: LabCase[]): string[] {
  const seen = new Set<string>();
  for (const c of cases) {
    for (const tag of caseTags(c)) {
      seen.add(tag);
    }
  }
  return Array.from(seen).sort(naturalCompare);
}
