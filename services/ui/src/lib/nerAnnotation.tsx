import React from "react";

export interface TagTheme {
  bg: string;
  border: string;
  label: string;
  /** Surface text of the entity — set when multiple entities share a merged span. */
  entityText?: string;
}

/** Consistent NER colour + label per SNOMED semantic tag */
export const SEMANTIC_TAG_THEME: Record<string, TagTheme> = {
  // -- Clinical findings & disorders
  clinicalfinding:          { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  clinical_finding:         { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  finding:                  { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  disease:                  { border: "#dc2626", bg: "#fecaca", label: "DISORDER" },
  disorder:                 { border: "#dc2626", bg: "#fecaca", label: "DISORDER" },
  morphologicabnormality:   { border: "#b45309", bg: "#fef3c7", label: "MORPHOLOGY" },
  morphologic_abnormality:  { border: "#b45309", bg: "#fef3c7", label: "MORPHOLOGY" },
  // -- Situations & context
  situation:                { border: "#6366f1", bg: "#e0e7ff", label: "SITUATION" },
  event:                    { border: "#4338ca", bg: "#ede9fe", label: "EVENT" },
  // -- Observables & anatomy
  observableentity:         { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  observable_entity:        { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  observable:               { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  bodystructure:            { border: "#db2777", bg: "#fce7f3", label: "ANATOMY" },
  body_structure:           { border: "#db2777", bg: "#fce7f3", label: "ANATOMY" },
  // -- Procedures & therapies
  procedure:                { border: "#2563eb", bg: "#bfdbfe", label: "PROCEDURE" },
  regimetherapy:            { border: "#1e40af", bg: "#eff6ff", label: "REGIMEN" },
  regime_therapy:           { border: "#1e40af", bg: "#eff6ff", label: "REGIMEN" },
  // -- Substances & drugs
  substance:                { border: "#7c3aed", bg: "#ddd6fe", label: "SUBSTANCE" },
  medication:               { border: "#7c3aed", bg: "#ddd6fe", label: "SUBSTANCE" },
  clinicaldrug:             { border: "#6d28d9", bg: "#ede9fe", label: "DRUG" },
  clinical_drug:            { border: "#6d28d9", bg: "#ede9fe", label: "DRUG" },
  medicinalproduct:         { border: "#6d28d9", bg: "#ede9fe", label: "DRUG" },
  medicinal_product:        { border: "#6d28d9", bg: "#ede9fe", label: "DRUG" },
  // -- Qualifiers, attributes & scales
  qualifiervalue:           { border: "#64748b", bg: "#f1f5f9", label: "QUALIFIER" },
  qualifier_value:          { border: "#64748b", bg: "#f1f5f9", label: "QUALIFIER" },
  attribute:                { border: "#6b7280", bg: "#f3f4f6", label: "ATTRIBUTE" },
  assessmentscale:          { border: "#0d9488", bg: "#ccfbf1", label: "SCALE" },
  assessment_scale:         { border: "#0d9488", bg: "#ccfbf1", label: "SCALE" },
  stagingscale:             { border: "#e11d48", bg: "#ffe4e6", label: "STAGING" },
  staging_scale:            { border: "#e11d48", bg: "#ffe4e6", label: "STAGING" },
  tumorstaging:             { border: "#e11d48", bg: "#ffe4e6", label: "STAGING" },
  tumor_staging:            { border: "#e11d48", bg: "#ffe4e6", label: "STAGING" },
  // -- Organisms & environment
  organism:                 { border: "#0f766e", bg: "#ccfbf1", label: "ORGANISM" },
  environment:              { border: "#65a30d", bg: "#ecfccb", label: "ENVIRONMENT" },
  // -- Occupations & social
  occupation:               { border: "#ca8a04", bg: "#fef9c3", label: "OCCUPATION" },
  // -- Physical objects & products
  physicalobject:           { border: "#78716c", bg: "#f5f5f4", label: "OBJECT" },
  physical_object:          { border: "#78716c", bg: "#f5f5f4", label: "OBJECT" },
  product:                  { border: "#0284c7", bg: "#e0f2fe", label: "PRODUCT" },
  recordartifact:           { border: "#71717a", bg: "#fafafa", label: "RECORD" },
  record_artifact:          { border: "#71717a", bg: "#fafafa", label: "RECORD" },
  // -- Custom extension types (X_ prefix)
  xdosage:                  { border: "#15803d", bg: "#dcfce7", label: "DOSAGE" },
  x_dosage:                 { border: "#15803d", bg: "#dcfce7", label: "DOSAGE" },
  xfrequency:               { border: "#0369a1", bg: "#e0f2fe", label: "FREQUENCY" },
  x_frequency:              { border: "#0369a1", bg: "#e0f2fe", label: "FREQUENCY" },
  // -- Fallbacks
  snomedconcept:            { border: "#1d4ed8", bg: "#dbeafe", label: "CONCEPT" },
  other:                    { border: "#64748b", bg: "#e2e8f0", label: "OTHER" },
};

export const DEFAULT_THEME: TagTheme = { border: "#1d4ed8", bg: "#dbeafe", label: "CONCEPT" };

export function themeForTag(tag: string | null | undefined): TagTheme {
  const key = (tag ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  return SEMANTIC_TAG_THEME[key] ?? DEFAULT_THEME;
}

/**
 * Extracts semantic tag from a SNOMED fully-specified name.
 * e.g. "Biopsy (procedure)" → "procedure"
 */
export function tagFromSnomedTerm(snomedTerm?: string | null): string | null {
  if (!snomedTerm) return null;
  const match = snomedTerm.match(/\(([^)]+)\)\s*$/);
  return match ? match[1] : null;
}

/**
 * Maps the new training-schema `assertion` field to a display theme,
 * falling back to semantic-tag colour for "present" entities.
 */
export function themeForAssertion(
  assertion: string | undefined | null,
  semanticTag?: string | null,
): TagTheme {
  switch ((assertion ?? "").toLowerCase()) {
    case "absent":
    case "negated":
      return { border: "#dc2626", bg: "#fee2e2", label: "NEGATED" };
    case "family":
    case "family_history":
      return { border: "#06b6d4", bg: "#cffafe", label: "FAMILY" };
    case "possible":
      return { border: "#ea580c", bg: "#ffedd5", label: "POSSIBLE" };
    case "hypothetical":
      return { border: "#9333ea", bg: "#f3e8ff", label: "HYPOTHETICAL" };
    default:
      return themeForTag(semanticTag);
  }
}

/**
 * A pre-merged, non-overlapping span ready for rendering.
 * Each span may carry multiple chips when several concepts share the same text.
 */
export interface AnnotatedSpan {
  start: number;
  end: number;
  /** One entry per concept at this span position */
  chips: TagTheme[];
  isSelected?: boolean;
  onClick?: (e: React.MouseEvent<HTMLSpanElement>) => void;
  title?: string;
}

/**
 * Build a CSS diagonal-stripe background for merged spans that contain
 * multiple overlapping entities. Each entity contributes its own color
 * band, making it immediately obvious that more than one entity is present.
 */
function buildMultiBackground(chips: TagTheme[]): string {
  const colors = chips.map((c) => c.bg);
  const step = Math.floor(100 / colors.length);
  const stops = colors.flatMap((c, i) => [`${c} ${i * step}%`, `${c} ${(i + 1) * step}%`]);
  return `linear-gradient(135deg, ${stops.join(", ")})`;
}

/**
 * Shared NER annotation renderer.
 * Takes pre-merged AnnotatedSpan[] and renders inline label chips below each span.
 * The parent container should set lineHeight: 3 to give room for the chips.
 * Overlapping entities that have been merged into a single span are visually
 * indicated by a dashed border and a diagonal-stripe background; each entity
 * in the merge gets its own chip showing the entity surface text.
 */
export function renderNerSpans(text: string, spans: AnnotatedSpan[]): React.ReactNode {
  if (!text) return null;
  if (spans.length === 0) return text;

  const sorted = [...spans].sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (const span of sorted) {
    if (span.start >= span.end || span.start > text.length || span.end > text.length) continue;
    if (span.start > cursor) parts.push(text.slice(cursor, span.start));

    const selected = span.isSelected ?? false;
    const multi = span.chips.length > 1;
    const boxBorder = selected
      ? "#4f46e5"
      : multi
        ? span.chips[0].border
        : span.chips[0].border;
    const boxBackground = selected
      ? "#c7d2fe"
      : multi
        ? buildMultiBackground(span.chips)
        : span.chips[0].bg;

    parts.push(
      <span
        key={`ner-${span.start}-${span.end}`}
        onClick={span.onClick}
        title={span.title ?? (multi ? span.chips.map((c) => c.entityText ?? c.label).join(" | ") : undefined)}
        style={{
          display: "inline-flex",
          flexDirection: "column",
          alignItems: "flex-start",
          verticalAlign: "bottom",
          margin: "0 1px",
          cursor: span.onClick ? "pointer" : "text",
        }}
      >
        <span
          style={{
            borderWidth: "1.5px",
            borderStyle: multi ? "dashed" : "solid",
            borderColor: boxBorder,
            borderRadius: "3px",
            padding: "1px 3px",
            background: boxBackground,
            transition: "background 0.15s",
          }}
        >
          {text.slice(span.start, span.end)}
        </span>
        {span.chips.map((chip, idx) => (
          <span
            key={idx}
            style={{
              backgroundColor: selected ? "#4f46e5" : chip.border,
              color: "#fff",
              fontSize: "0.6rem",
              fontWeight: 700,
              padding: "1px 4px",
              borderRadius: "2px",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              whiteSpace: "nowrap",
              lineHeight: 1.4,
              marginTop: idx === 0 ? "1px" : "2px",
              maxWidth: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={chip.entityText ? `${chip.entityText} · ${chip.label}` : chip.label}
          >
            {selected
              ? "SELECTED"
              : chip.entityText
                ? `${chip.entityText} · ${chip.label}`
                : chip.label}
          </span>
        ))}
      </span>,
    );

    cursor = span.end;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}
