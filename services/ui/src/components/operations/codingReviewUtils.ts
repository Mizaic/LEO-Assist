import { keyframes } from "@mui/material/styles";

export const safetyPulse = keyframes`
  0%, 100% { box-shadow: 0 0 4px 0 rgba(211, 47, 47, 0.35); }
  50%      { box-shadow: 0 0 14px 5px rgba(211, 47, 47, 0.55); }
`;

export const ASSERTION_OPTIONS = [
  "absent",
  "cancelled",
  "declined",
  "family",
  "historical",
  "hypothetical",
  "planned",
  "possible",
  "present",
  "refuted",
] as const;

export const ENTITY_LABEL_OPTIONS = [
  "body_structure",
  "clinical_drug",
  "disorder",
  "event",
  "finding",
  "medicinal_product",
  "observable_entity",
  "procedure",
  "qualifier_value",
  "situation",
  "substance",
];

export const LABEL_COLORS: Record<string, string> = {
  finding: "#6366f1",
  disorder: "#dc2626",
  procedure: "#2563eb",
  observable_entity: "#0891b2",
  qualifier_value: "#7c3aed",
  situation: "#ca8a04",
  substance: "#059669",
  medicinal_product: "#d946ef",
  event: "#ea580c",
  body_structure: "#64748b",
};

export interface CaseRecord {
  review_id: string;
  label_id?: string;
  entity_text: string;
  entity_label: string;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  encounter_text: string;
  source: string;
  assertion?: string;
  suggested_label?: string | null;
  tag_mismatch_delta?: number | null;
}

export interface SiblingEntity {
  review_id: string;
  entity_text: string;
  entity_label: string;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  assertion: string;
  resolved: boolean;
  resolved_concept_id: string | null;
  resolved_term: string | null;
}

export function isClinicalSafetyWarning(
  warning: string | null | undefined,
): boolean {
  if (!warning) return false;
  return (
    /^lab-value guard/i.test(warning) ||
    /clinical safety/i.test(warning) ||
    /\blab result\b/i.test(warning)
  );
}

export function isLabValueWarning(warning: string): boolean {
  return /^lab-value guard/i.test(warning) || /\blab result\b/i.test(warning);
}

export function warningHeadline(warning: string): string {
  if (isLabValueWarning(warning)) {
    return "Clinical safety: this is NOT a diagnosis.";
  }
  return "LEO says: this procedure was not performed.";
}

/**
 * LEO naturally quotes the key phrase that triggered the warning, e.g.
 * "the encounter text explicitly states 'awaiting appt for biopsy'".
 * We pull the first quoted phrase (4-80 chars) as the suggested suppress phrase.
 * Falls back to a short window around the entity in the encounter text.
 */
export function extractSuggestedPhrase(
  warning: string,
  entityText: string,
  encounterText: string,
): string {
  const quoted = warning.match(/'([^']{4,80})'/);
  if (quoted) return quoted[1];

  const lower = encounterText.toLowerCase();
  const idx = lower.indexOf(entityText.toLowerCase());
  if (idx >= 0) {
    const start = Math.max(0, idx - 15);
    const end = Math.min(encounterText.length, idx + entityText.length + 15);
    return encounterText.slice(start, end).trim();
  }

  return "";
}

export async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...init?.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
