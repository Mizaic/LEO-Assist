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

// Maps SNOMED display strings (space/slash-separated) and legacy aliases to the
// canonical underscore form used in training data and the NER model.
const _SPACE_FORM_MAP: Record<string, EntitySemanticLabel> = {
  "observable entity": "observable_entity",
  "qualifier value": "qualifier_value",
  "body structure": "body_structure",
  "tumor staging": "tumor_staging",
  "assessment scale": "assessment_scale",
  "staging scale": "staging_scale",
  "regime/therapy": "regime_therapy",
  "record artifact": "record_artifact",
  "physical object": "physical_object",
  "morphologic abnormality": "morphologic_abnormality",
  "clinical drug": "clinical_drug",
  "medicinal product": "medicinal_product",
  snomedconcept: "finding",
};

/**
 * Map any raw label string (canonical, SNOMED display, or legacy alias) to the
 * canonical underscore form used in training data and MUI selects.
 */
export function coerceEntitySemanticLabel(raw: string | undefined | null): EntitySemanticLabel {
  const s = String(raw ?? "").trim();
  if (VALID_ENTITY_SEMANTIC_LABEL_SET.has(s)) {
    return s as EntitySemanticLabel;
  }
  const lower = s.toLowerCase();
  const mapped = _SPACE_FORM_MAP[lower];
  if (mapped) return mapped;
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
