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
      .map((entry, index, all) => {
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
        const bodySiteConceptId = String(entry.body_site_concept_id ?? "").trim();
        const bodySiteTerm = String(entry.body_site_term ?? "").trim();
        const rawRelations = Array.isArray(entry.relations)
          ? (entry.relations as Array<Record<string, unknown>>)
          : Array.isArray(entry.__relations)
            ? (entry.__relations as Array<Record<string, unknown>>)
            : [];
        const relations = rawRelations
          .map((row) => {
            const type = String(row.type ?? "").trim().toLowerCase();
            const targetIdx = Number(row.target_idx);
            if (!type || Number.isNaN(targetIdx)) return null;
            return {
              type,
              target_idx: targetIdx,
              target_text: String(row.target_text ?? "").trim() || undefined,
              confidence: typeof row.confidence === "number" ? Number(row.confidence) : undefined,
            };
          })
          .filter((row): row is NonNullable<typeof row> => Boolean(row));

        if (!relations.some((row) => row.type === "finding_site")) {
          const legacySite = bodySiteTerm || String(entry.body_site ?? "").trim();
          if (legacySite) {
            const targetIdx = all.findIndex((target, idx) => {
              if (idx === index || !target || typeof target !== "object") return false;
              const text = String(target.text ?? "").trim().toLowerCase();
              const term = String(target.snomed_term ?? target.term ?? "").trim().toLowerCase();
              return legacySite.toLowerCase() === text || legacySite.toLowerCase() === term;
            });
            if (targetIdx >= 0) {
              relations.push({
                type: "finding_site",
                target_idx: targetIdx,
                target_text: String((all[targetIdx] as Record<string, unknown>).text ?? "").trim() || undefined,
                confidence: 1,
              });
            }
          }
        }
        return {
          ...entry,
          text,
          snomed_concept_id: snomedConceptId || undefined,
          snomed_term: snomedTerm || undefined,
          body_site_concept_id: bodySiteConceptId || undefined,
          body_site_term: bodySiteTerm || undefined,
          relations,
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

// -- Entity label colour palette (shared across chart, chips and pills) ------
//
// Keys are lowercase canonical labels.  Use entityLabelColour() for lookup --
// it lowercases the input so it works with both "DISORDER" and "disorder".

export const ENTITY_LABEL_COLOURS: Record<string, string> = {
  disorder: "#1565c0",
  finding: "#2e7d32",
  procedure: "#6a1b9a",
  observable_entity: "#00838f",
  qualifier_value: "#e65100",
  substance: "#4e342e",
  medicinal_product: "#ad1457",
  clinical_drug: "#c62828",
  situation: "#558b2f",
  event: "#f57f17",
  body_structure: "#37474f",
  x_temporal: "#0277bd",
  x_dosage: "#4527a0",
  x_frequency: "#283593",
  x_route: "#00695c",
  assessment_scale: "#5d4037",
  attribute: "#827717",
  environment: "#004d40",
  morphologic_abnormality: "#880e4f",
  occupation: "#795548",
  organism: "#1b5e20",
  physical_object: "#263238",
  product: "#b71c1c",
  record_artifact: "#3e2723",
  regime_therapy: "#4a148c",
  staging_scale: "#006064",
  tumor_staging: "#bf360c",
};

/** Fallback colour for unknown / unlabelled entities. */
export const ENTITY_COLOUR_FALLBACK = "#78909c";

/**
 * Return a hex colour for a given entity label.
 * Case-insensitive: works with both "DISORDER" (server/chart) and "disorder" (UI objects).
 */
export function entityLabelColour(label: string | undefined | null): string {
  const key = String(label ?? "").toLowerCase();
  return ENTITY_LABEL_COLOURS[key] ?? ENTITY_COLOUR_FALLBACK;
}
