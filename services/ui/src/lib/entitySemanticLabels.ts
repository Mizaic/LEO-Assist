/** Canonical SNOMED CT semantic tag strings for NER entity types (training / gold UI). */
export const VALID_ENTITY_SEMANTIC_LABELS = [
  "assessment_scale",
  "attribute",
  "body_structure",
  "clinical_drug",
  "disorder",
  "environment",
  "event",
  "finding",
  "medicinal_product",
  "morphologic_abnormality",
  "observable_entity",
  "occupation",
  "organism",
  "physical_object",
  "procedure",
  "product",
  "qualifier_value",
  "record_artifact",
  "regime_therapy",
  "situation",
  "staging_scale",
  "substance",
  "tumor_staging",
  "X_DOSAGE",
  "X_FREQUENCY",
  "X_ROUTE",
  "X_TEMPORAL",
] as const;

export type EntitySemanticLabel = (typeof VALID_ENTITY_SEMANTIC_LABELS)[number];

const VALID_ENTITY_SEMANTIC_LABEL_SET = new Set<string>(VALID_ENTITY_SEMANTIC_LABELS);

/**
 * Map legacy Neo4j / sync placeholders (e.g. SnomedConcept) to a valid semantic tag
 * for MUI Selects and training entity JSON.
 */
export function coerceEntitySemanticLabel(raw: string | undefined | null): EntitySemanticLabel {
  const s = String(raw ?? "").trim();
  if (VALID_ENTITY_SEMANTIC_LABEL_SET.has(s)) {
    return s as EntitySemanticLabel;
  }
  const lower = s.toLowerCase();
  if (lower === "snomedconcept") {
    return "finding";
  }
  if (VALID_ENTITY_SEMANTIC_LABEL_SET.has(lower)) {
    return lower as EntitySemanticLabel;
  }
  return "finding";
}

export function normaliseEntitySemanticRows<T extends { label?: string | null }>(
  rows: T[],
): T[] {
  return rows.map((row) => ({
    ...row,
    label: coerceEntitySemanticLabel(row.label),
  }));
}
