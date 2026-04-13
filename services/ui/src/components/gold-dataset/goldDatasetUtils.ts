import {
  normaliseEntitySemanticRows,
  type EntitySemanticLabel,
} from "@/lib/entitySemanticLabels";
import type { Entity } from "./goldDatasetTypes";

export const ASSERTION_LABEL: Record<string, string> = {
  present: "Present",
  absent: "Absent",
  refuted: "Refuted",
  possible: "Possible",
  uncertain: "Uncertain",
  historical: "Historical",
  family: "Family history",
  hypothetical: "Hypothetical",
  planned: "Planned",
  cancelled: "Cancelled",
  declined: "Declined",
};

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
  "uncertain",
] as const;

export function parseEntities(json: string | null): Entity[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) return [];
    const rows = parsed
      .filter(
        (entry): entry is Record<string, unknown> =>
          Boolean(entry) && typeof entry === "object",
      )
      .map((entry) => {
        const coding =
          entry.coding && typeof entry.coding === "object"
            ? (entry.coding as Record<string, unknown>)
            : {};
        const snomedConceptId = String(
          entry.snomed_concept_id ??
            entry.concept_id ??
            coding.snomed_concept_id ??
            "",
        ).trim();
        const snomedTerm = String(
          entry.snomed_term ??
            entry.term ??
            entry.preferred_term ??
            coding.snomed_term ??
            "",
        ).trim();
        const text = String(entry.text ?? "").trim();
        return {
          ...entry,
          text,
          snomed_concept_id: snomedConceptId || undefined,
          snomed_term: snomedTerm || undefined,
        } as Entity;
      });
    return normaliseEntitySemanticRows(rows);
  } catch {
    return [];
  }
}

export function formatAssertion(assertion: string | undefined): string {
  const key = (assertion ?? "present").toLowerCase().replace(/_/g, " ").trim();
  return ASSERTION_LABEL[key] ?? (key.charAt(0).toUpperCase() + key.slice(1));
}

export function isNonPresent(assertion: string | undefined): boolean {
  const key = (assertion ?? "present").toLowerCase().trim();
  return key !== "present";
}

export function assertionColor(
  assertion: string | undefined,
): "default" | "success" | "warning" | "info" | "error" {
  switch ((assertion ?? "present").toLowerCase()) {
    case "present":
      return "success";
    case "possible":
    case "uncertain":
    case "hypothetical":
    case "planned":
      return "warning";
    case "historical":
    case "family":
      return "info";
    case "absent":
    case "refuted":
    case "cancelled":
    case "declined":
      return "error";
    default:
      return "default";
  }
}

export function assertionSummary(entities: Entity[]): string | null {
  const counts: Record<string, number> = {};
  for (const e of entities) {
    const key = formatAssertion(e.assertion);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  const parts = Object.entries(counts)
    .sort(([a], [b]) => (a === "Present" ? -1 : b === "Present" ? 1 : 0))
    .map(([k, v]) => `${v} ${k.toLowerCase()}`);
  if (parts.length <= 1 && counts["Present"] === entities.length) return null;
  return parts.join(" - ");
}

export function truncate(text: string, max = 160): string {
  if (!text) return "-";
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function coerceEntityLabel(label: string | undefined): EntitySemanticLabel {
  return (label ?? "finding") as EntitySemanticLabel;
}
