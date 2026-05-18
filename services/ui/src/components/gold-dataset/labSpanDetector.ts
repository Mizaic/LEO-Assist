/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
// Client-side mirror of libs/training/lab_span_detector.py.
//
// Produces the same "lab triple" diagnostic used by the Python backfill
// script so the reviewer sees the same soft warnings the health panel
// surfaces. Detector is deliberately strict (requires a Read / CTV3 code)
// to keep false positives at zero.
//
// Keep in sync with libs/training/lab_span_detector.py.

import type { Entity } from "./goldDatasetTypes";

export const LAB_LABELS = {
  procedure: "procedure",
  observable: "observable_entity",
  finding: "finding",
} as const;

export type LabLabel = (typeof LAB_LABELS)[keyof typeof LAB_LABELS];

// Read / CTV3 code like "(42X..)", "(XE2pb)". Must contain at least one
// digit so drug brand names in parens (e.g. "(Fermagon)") are not mistaken
// for codes.
const READ_CODE_RE = /\(([A-Za-z0-9.]*[0-9][A-Za-z0-9.]*)\)/;

// Numeric value token: optional <>, optional space, digits, optional decimal.
const VALUE_RE = /^[<>]?\s*\d+(?:\.\d+)?/;

// Unit token: letters/digits/%/ ^ / *; caller verifies it is a medical unit.
const UNIT_RE = /^[A-Za-z0-9%/^*]+/;

// Reference range like "[20 - 80]" or "[< 10]".
const RANGE_RE = /^\[[^\]]{1,40}\]/;

// Whitespace-only between Read-code close and the numeric value. Any dash,
// colon or prose inbetween means the text is a disorder/finding qualifier.
const POST_CODE_TO_VALUE_RE = /^[ \t]+(?=[<>]?[ \t]*\d)/;

const INTERPRETATION_RE =
  /[-,;]\s*(?:outside reference range|abnormal[^,;.\n]*|not detected[^,;.\n]*|detected by[^,;.\n]*|satisfactory[^,;.\n]*|no further action[^,;.\n]*|within reference range|within normal limits|low|high|raised|elevated)/i;

const PROSE_STOPWORDS = new Set([
  "the",
  "and",
  "or",
  "but",
  "if",
  "then",
  "a",
  "an",
  "patient",
  "reports",
  "complaining",
  "history",
  "of",
]);

const PROSE_PREFIXES = new Set([
  "problem",
  "major",
  "history",
  "complaint",
  "issue",
  "diagnosis",
  "impression",
  "plan",
  "assessment",
  "reason",
  "episode",
  "note",
]);

// Must match libs/training/lab_span_detector.py::_KNOWN_UNIT_TOKENS.
const KNOWN_UNIT_TOKENS = new Set([
  "nmol", "umol", "mmol", "mol", "mcg", "meq", "miu",
  "ng", "pg", "fg", "ug", "mg", "g", "kg",
  "fl", "pl", "ul", "ml", "dl", "l", "cl",
  "iu", "u", "cells", "copies",
  "pct", "percent", "bpm", "mmhg", "kpa",
  "cm", "mm", "m", "kgm",
  "degc", "degf", "c", "f",
  "min", "hr", "sec", "s",
]);

export interface LabDiagnostic {
  isLab: boolean;
  missing: LabLabel[];
  hasInterpretation: boolean;
  hasValueUnit: boolean;
  readCode: string | null;
}

function looksLikeMedicalUnit(token: string): boolean {
  if (!token) return false;
  const lower = token.toLowerCase();
  if (lower.includes("/") || lower.includes("^") || lower.includes("%")) {
    return /[A-Za-z%/^]/.test(lower);
  }
  if (lower.startsWith("x10")) return true;
  return KNOWN_UNIT_TOKENS.has(lower);
}

function looksLikeProse(testName: string): boolean {
  const tokens = testName
    .split(/\s+/)
    .map((t) => t.toLowerCase())
    .filter(Boolean);
  if (tokens.length === 0) return true;
  const first = tokens[0].replace(/[:.,;]+$/, "");
  if (PROSE_PREFIXES.has(first)) return true;
  if (tokens.length > 8) return true;
  const stopHits = tokens.filter((t) => PROSE_STOPWORDS.has(t)).length;
  return stopHits >= 2;
}

function findValueUnitEnd(text: string, startAt: number): {
  end: number;
  matched: boolean;
} {
  const tail = text.slice(startAt);
  if (!tail.trim()) return { end: startAt, matched: false };
  const trimmed = tail.replace(/^[ \t]+/, "");
  const valueOffset = tail.length - trimmed.length;
  const valueMatch = VALUE_RE.exec(trimmed);
  if (valueMatch === null) return { end: startAt, matched: false };

  const valueEnd = startAt + valueOffset + valueMatch[0].length;
  const afterValue = text.slice(valueEnd);
  const leadingWs = afterValue.length - afterValue.replace(/^[ \t]+/, "").length;
  const unitStart = valueEnd + leadingWs;
  const unitMatch = UNIT_RE.exec(text.slice(unitStart));

  if (unitMatch === null || !looksLikeMedicalUnit(unitMatch[0])) {
    return { end: startAt, matched: false };
  }
  let cursor = unitStart + unitMatch[0].length;
  const rangeTail = text.slice(cursor);
  const rangeLeadingWs = rangeTail.length - rangeTail.replace(/^[ \t]+/, "").length;
  const rangeMatch = RANGE_RE.exec(text.slice(cursor + rangeLeadingWs));
  if (rangeMatch !== null) {
    cursor += rangeLeadingWs + rangeMatch[0].length;
  }
  return { end: cursor, matched: true };
}

function findInterpretationEnd(text: string, startAt: number): {
  end: number;
  matched: boolean;
} {
  const tail = text.slice(startAt);
  const match = INTERPRETATION_RE.exec(tail);
  if (match === null) return { end: startAt, matched: false };
  return { end: startAt + match.index + match[0].length, matched: true };
}

function summariseExistingLabLabels(entities: Entity[]): Set<LabLabel> {
  const labels = new Set<LabLabel>();
  for (const ent of entities) {
    const raw = String(ent.label ?? ent.semantic_tag ?? "")
      .toLowerCase()
      .replace(/\s/g, "_");
    if (raw === LAB_LABELS.procedure) labels.add(LAB_LABELS.procedure);
    else if (raw === LAB_LABELS.observable) labels.add(LAB_LABELS.observable);
    else if (raw === LAB_LABELS.finding) labels.add(LAB_LABELS.finding);
  }
  return labels;
}

export function diagnoseLabTripleCoverage(
  text: string,
  entities: Entity[],
): LabDiagnostic {
  const empty: LabDiagnostic = {
    isLab: false,
    missing: [],
    hasInterpretation: false,
    hasValueUnit: false,
    readCode: null,
  };
  if (!text || !text.trim()) return empty;

  const codeMatch = READ_CODE_RE.exec(text);
  if (codeMatch === null) return empty;

  const codeStart = codeMatch.index;
  const codeEnd = codeStart + codeMatch[0].length;
  const readCode = codeMatch[1];
  const testName = text.slice(0, codeStart).trim();

  if (!testName || looksLikeProse(testName)) return empty;

  if (POST_CODE_TO_VALUE_RE.exec(text.slice(codeEnd)) === null) return empty;

  const { end: valueEnd, matched: hasValueUnit } = findValueUnitEnd(
    text,
    codeEnd,
  );
  const { matched: hasInterp } = findInterpretationEnd(text, valueEnd);

  if (!hasValueUnit) return empty;

  const existing = summariseExistingLabLabels(entities);
  const missing: LabLabel[] = [];
  if (!existing.has(LAB_LABELS.procedure)) missing.push(LAB_LABELS.procedure);
  if (hasValueUnit && !existing.has(LAB_LABELS.observable)) {
    missing.push(LAB_LABELS.observable);
  }
  if (hasInterp && !existing.has(LAB_LABELS.finding)) {
    missing.push(LAB_LABELS.finding);
  }

  return {
    isLab: true,
    missing,
    hasInterpretation: hasInterp,
    hasValueUnit,
    readCode,
  };
}
