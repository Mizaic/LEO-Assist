import React from "react";

export interface TagTheme {
  bg: string;
  border: string;
  label: string;
}

/** Consistent NER colour + label per SNOMED semantic tag */
export const SEMANTIC_TAG_THEME: Record<string, TagTheme> = {
  situation:         { border: "#6366f1", bg: "#e0e7ff", label: "SITUATION" },
  clinicalfinding:   { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  clinical_finding:  { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  finding:           { border: "#16a34a", bg: "#d1fae5", label: "FINDING" },
  disease:           { border: "#dc2626", bg: "#fecaca", label: "DISORDER" },
  disorder:          { border: "#dc2626", bg: "#fecaca", label: "DISORDER" },
  observableentity:  { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  observable_entity: { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  observable:        { border: "#d97706", bg: "#fef3c7", label: "OBSERVABLE" },
  procedure:         { border: "#2563eb", bg: "#bfdbfe", label: "PROCEDURE" },
  substance:         { border: "#7c3aed", bg: "#ddd6fe", label: "SUBSTANCE" },
  medication:        { border: "#7c3aed", bg: "#ddd6fe", label: "SUBSTANCE" },
  snomedconcept:     { border: "#1d4ed8", bg: "#dbeafe", label: "CONCEPT" },
  other:             { border: "#64748b", bg: "#e2e8f0", label: "OTHER" },
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
  switch (assertion) {
    case "absent":  return { border: "#dc2626", bg: "#fee2e2", label: "NEGATED" };
    case "family":  return { border: "#06b6d4", bg: "#cffafe", label: "FAMILY" };
    default:        return themeForTag(semanticTag);
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
 * Shared NER annotation renderer.
 * Takes pre-merged AnnotatedSpan[] and renders inline label chips below each span.
 * The parent container should set lineHeight: 3 to give room for the chips.
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
    const boxBorder = selected
      ? "#4f46e5"
      : span.chips.length === 1
        ? span.chips[0].border
        : "#94a3b8";
    const boxBg = selected
      ? "#c7d2fe"
      : span.chips.length === 1
        ? span.chips[0].bg
        : "#f8fafc";

    parts.push(
      <span
        key={`ner-${span.start}-${span.end}`}
        onClick={span.onClick}
        title={span.title}
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
            border: `1.5px solid ${boxBorder}`,
            borderRadius: "3px",
            padding: "1px 3px",
            backgroundColor: boxBg,
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
              marginTop: "1px",
            }}
          >
            {selected ? "SELECTED" : chip.label}
          </span>
        ))}
      </span>,
    );

    cursor = span.end;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}
