/**
 * Pure-function auto-detector for referral form structure.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721, DI-A0E69E38
 */

import {
  classifyNamedSection,
  clinicalEntityText,
  extraNamedHeaders,
  observableItems,
  withBmiSection,
  withSplitScales,
} from "./formSchemaDetectExtras";

/**
 * The section types the checkbox normaliser can dispatch on. This must stay
 * in step with SectionType in libs/pipeline/form_schema_normalizer.py; a
 * value outside it leaves the tick boxes unprocessed.
 */
export const SECTION_TYPES = [
  "checkbox_single",
  "checkbox_yesno",
  "checkbox_multi",
  "free_text",
  "scale",
  "ordered_tests",
  "observable",
  "admin",
  "template_noise",
] as const;

export type SectionType = (typeof SECTION_TYPES)[number];

/** Free text neither fabricates a finding nor hides one. */
export const SAFE_SECTION_TYPE: SectionType = "free_text";

// Values seen from the server that map cleanly onto the vocabulary. Keep
// this to observed evidence only; a guessed alias is a silent wrong answer.
const SECTION_TYPE_ALIASES: Record<string, SectionType> = {
  checkbox: "checkbox_multi",
};

/** Return the nearest usable section type for a value from the server. */
export function coerceSectionType(value: unknown): SectionType {
  const text = typeof value === "string" ? value.trim() : "";
  if ((SECTION_TYPES as readonly string[]).includes(text)) {
    return text as SectionType;
  }
  return SECTION_TYPE_ALIASES[text.toLowerCase()] ?? SAFE_SECTION_TYPE;
}

export interface AnalyteEntry {
  label: string;
  snomed_code: string;
  display: string;
}

export interface FormSchemaItem {
  pattern: string;
  entity_text: string;
  semantic_tag: string;
  assertion: string;
  // ordered_tests enrichment fields
  procedure_snomed?: string;
  procedure_display?: string;
  analytes?: AnalyteEntry[];
  value_placeholder?: string;
}

export interface BorrowedFrom {
  org: string;
  service: string;
  form_name: string;
  confidence: number;
}

export interface FormSchemaSection {
  section_id: string;
  section_type: SectionType;
  label: string;
  start_pattern: string;
  items: FormSchemaItem[];
  semantic_tags?: string[];
  borrowed_from?: BorrowedFrom;
}

export { detectFormName } from "./formSchemaDetectExtras";

const CHECKED = /\[(?:X|x|\*)\]/;
const UNCHECKED = /\[\s*\]/;
const YES_NO_ROW = /Yes\s*\[(?:X|x)?\s*\]\s*No\s*\[(?:X|x)?\s*\]/i;
const NUMBERED_SCALE = /\b1\.\s+\w[\w\s]+\[(?:X|\s*)\]/;
const MANDATORY_TESTS =
  /mandatory|fbc|lft|ues|urea|calcium|creatinine|bloods?\s+done/i;
const SECTION_HEADER = /^section\s+([a-z]|\d{1,2})\b(?:\s*[:.])?/i;
const NAMED_HEADER =
  /^(patient details|practice details|minimum dataset|for trust use|hospital number|hospital use only)/i;
const ADMIN_HEADER =
  /^(patient details|practice details|for trust use|hospital number|hospital use only)/i;
// Numbered forms print the admin heading after the number, e.g.
// "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS".
const ADMIN_NUMBERED_HEADER = /^section\s+\d{1,2}\b.*\bdemographic/i;

export function normalizeFormText(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|tr|h[1-6]|li)>/gi, "\n")
    .replace(/<\/td>/gi, " | ")
    .replace(/<[^>]+>/g, " ")
    .replace(/^\s*\|\s*/gm, "")
    .replace(/\s*\|\s*$/gm, "")
    .replace(/(^|[^A-Za-z])(section\s+(?:[a-z]|\d{1,2})\b)/gi, "$1\n$2")
    .replace(/[ \t]+/g, " ");
}

function _countBoxes(lines: string[]): { checked: number; unchecked: number } {
  let checked = 0;
  let unchecked = 0;
  for (const ln of lines) {
    if (CHECKED.test(ln)) checked++;
    if (UNCHECKED.test(ln)) unchecked++;
  }
  return { checked, unchecked };
}

function _classifyLines(lines: string[]): SectionType {
  if (lines.some((ln) => MANDATORY_TESTS.test(ln))) return "ordered_tests";
  const { checked, unchecked } = _countBoxes(lines);
  if (checked + unchecked === 0) return "free_text";
  if (lines.some((ln) => YES_NO_ROW.test(ln))) return "checkbox_yesno";
  if (lines.some((ln) => NUMBERED_SCALE.test(ln))) return "scale";
  if (unchecked > 0 && checked <= 1) return "checkbox_single";
  if (checked > 1) return "checkbox_multi";
  return "checkbox_single";
}

function _extractSingleItems(lines: string[]): FormSchemaItem[] {
  const items: FormSchemaItem[] = [];
  const itemRe = /([A-Za-z][A-Za-z\s]{1,40}?)\s*\[(?:X|x|\*|\s*)\]/g;
  for (const ln of lines) {
    for (const match of ln.matchAll(itemRe)) {
      const label = match[1].replace(/^\d+[.)]\s*/, "").trim();
      if (label.length < 2 || items.some((i) => i.pattern === label)) continue;
      items.push({
        pattern: label,
        entity_text: clinicalEntityText(label),
        semantic_tag: "finding",
        assertion: "present",
      });
    }
  }
  return items;
}

function _extractYesNoItems(lines: string[]): FormSchemaItem[] {
  const items: FormSchemaItem[] = [];
  for (const ln of lines) {
    const match = ln.match(/^(.+?)\s*[|]\s*Yes/i) || ln.match(/^(B\d+\..+?)\s+Yes\s*\[/i);
    if (!match) continue;
    const label = match[1].replace(/^\s*[A-Z]\d*[.:]?\s*/, "").trim();
    if (label.length < 3) continue;
    items.push({
      pattern: match[1].trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
      entity_text: label,
      semantic_tag: "finding",
      assertion: "present",
    });
  }
  return items;
}

function _extractScaleItems(lines: string[]): FormSchemaItem[] {
  const items: FormSchemaItem[] = [];
  for (const ln of lines) {
    for (const part of ln.split(/\d+\.\s+/).filter(Boolean)) {
      const label = part.replace(/\[(?:X|\s*)\]/g, "").trim();
      if (label.length < 2) continue;
      items.push({
        pattern: label,
        entity_text: label,
        semantic_tag: "finding",
        assertion: "present",
      });
    }
  }
  return items;
}

function _buildItems(sectionType: SectionType, bodyLines: string[]): FormSchemaItem[] {
  if (sectionType === "observable") return observableItems(bodyLines);
  if (sectionType === "checkbox_single" || sectionType === "checkbox_multi") {
    return _extractSingleItems(bodyLines);
  }
  if (sectionType === "checkbox_yesno") return _extractYesNoItems(bodyLines);
  if (sectionType === "scale") return _extractScaleItems(bodyLines);
  return [];
}

function _startPattern(label: string): string {
  const letter = label.match(SECTION_HEADER)?.[1];
  if (letter && /^\d+$/.test(letter)) return `(?i)section\\s+${letter}\\b`;
  if (letter) return `(?i)section\\s+${letter.toLowerCase()}:`;
  const first = label.split(/\s+/).slice(0, 3).join("\\s+");
  return `(?i)${first}`;
}

export function detectSections(text: string): FormSchemaSection[] {
  if (!text.trim()) return [];
  const lines = normalizeFormText(text).split("\n");
  const breakpoints: Array<{ idx: number; label: string }> = [];
  lines.forEach((ln, idx) => {
    const stripped = ln.replace(/^\s*[#]+\s*/, "").trim();
    if (SECTION_HEADER.test(stripped) || NAMED_HEADER.test(stripped)) {
      breakpoints.push({ idx, label: stripped });
      return;
    }
    const extra = extraNamedHeaders(stripped);
    if (extra) breakpoints.push({ idx, label: extra });
  });
  if (!breakpoints.length) return [];
  const sections: FormSchemaSection[] = [];
  for (let i = 0; i < breakpoints.length; i++) {
    const { idx, label } = breakpoints[i];
    const nextIdx = i + 1 < breakpoints.length ? breakpoints[i + 1].idx : lines.length;
    const bodyLines = lines.slice(idx + 1, nextIdx).filter((ln) => ln.trim());
    const namedType = classifyNamedSection(label, bodyLines);
    const isAdmin = ADMIN_HEADER.test(label) || ADMIN_NUMBERED_HEADER.test(label);
    const sectionType: SectionType = namedType
      ? namedType
      : isAdmin
        ? "admin"
        : _classifyLines(bodyLines);
    const letter = label.match(SECTION_HEADER)?.[1] ?? `H${i}`;
    sections.push({
      section_id: letter.toUpperCase(),
      section_type: sectionType,
      label,
      start_pattern: _startPattern(label),
      items: _buildItems(sectionType, bodyLines),
    });
  }
  return withBmiSection(withSplitScales(sections), lines);
}
