/**
 * Pure-function auto-detector for referral form structure.
 * Analyses form text and proposes section types and checkbox items.
 * No DOM or network dependencies -- fully testable as a unit.
 *
 * Atlas trace: DI-5C9CA57B
 */

export type SectionType =
  | "checkbox_single"
  | "checkbox_yesno"
  | "checkbox_multi"
  | "free_text"
  | "scale"
  | "ordered_tests"
  | "admin"
  | "template_noise";

export interface FormSchemaItem {
  pattern: string;
  entity_text: string;
  semantic_tag: string;
  assertion: string;
}

export interface FormSchemaSection {
  section_id: string;
  section_type: SectionType;
  label: string;
  start_pattern: string;
  items: FormSchemaItem[];
}

// -- Detection helpers -------------------------------------------------------

const CHECKED = /\[(?:X|x|\*)\]/;
const UNCHECKED = /\[\s*\]/;
const YES_NO_ROW = /Yes\s*\[(?:X|x)?\s*\]\s*No\s*\[(?:X|x)?\s*\]/i;
const NUMBERED_SCALE = /\b1\.\s+\w[\w\s]+\[(?:X|\s*)\]/;
const MANDATORY_TESTS =
  /mandatory|fbc|lft|ues|urea|calcium|creatinine|blood\s+results?/i;
const SECTION_HEADER = /^section\s+([a-z])\b(?:\s*[:.])?/i;
// Named headers are top-level form sections NOT covered by Section X: pattern.
// Clinical Frailty Scale / ECOG / Performance Status appear as body lines
// within Section E, not as independent top-level sections.
const NAMED_HEADER =
  /^(patient details|practice details|minimum dataset|for trust use|hospital number)/i;
const ADMIN_HEADER =
  /^(patient details|practice details|minimum dataset|for trust use|hospital number)/i;

export function normalizeFormText(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|tr|h[1-6]|li)>/gi, "\n")
    .replace(/<\/td>/gi, " | ")
    .replace(/<[^>]+>/g, " ")
    .replace(/^\s*\|\s*/gm, "")
    .replace(/\s*\|\s*$/gm, "")
    .replace(/(^|[^A-Za-z])(section\s+[a-z]\b)/gi, "$1\n$2")
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
  // Check for test lists first -- they may have no checkboxes at all.
  const hasTests = lines.some((ln) => MANDATORY_TESTS.test(ln));
  if (hasTests) return "ordered_tests";

  const { checked, unchecked } = _countBoxes(lines);
  const total = checked + unchecked;

  if (total === 0) return "free_text";

  const hasYesNo = lines.some((ln) => YES_NO_ROW.test(ln));
  if (hasYesNo) return "checkbox_yesno";

  const hasScale = lines.some((ln) => NUMBERED_SCALE.test(ln));
  if (hasScale) return "scale";

  if (unchecked > 0 && checked <= 1) return "checkbox_single";
  if (checked > 1) return "checkbox_multi";

  return "checkbox_single";
}

function _extractSingleItems(lines: string[]): FormSchemaItem[] {
  const items: FormSchemaItem[] = [];
  // Match a label word/phrase that directly precedes a checkbox marker.
  // The label ends right before the [ ] or [X] on the same line.
  const itemRe = /([A-Za-z][A-Za-z\s]{1,40}?)\s*\[(?:X|x|\*|\s*)\]/g;
  for (const ln of lines) {
    const matches = [...ln.matchAll(itemRe)];
    for (const match of matches) {
      const label = match[1]
        .replace(/^\d+[.)]\s*/, "")
        .trim();
      if (label.length < 2) continue;
      if (items.some((i) => i.pattern === label)) continue;
      items.push({
        pattern: label,
        entity_text: `${label} (checked on referral form)`,
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
    const match = ln.match(/^(.+?)\s*[|]\s*Yes/i);
    if (!match) continue;
    const label = match[1]
      .replace(/^\s*[A-Z]\d*[.:]?\s*/, "")
      .trim();
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
    const parts = ln.split(/\d+\.\s+/).filter(Boolean);
    for (const part of parts) {
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

function _buildItems(
  sectionType: SectionType,
  bodyLines: string[],
): FormSchemaItem[] {
  if (sectionType === "checkbox_single" || sectionType === "checkbox_multi") {
    return _extractSingleItems(bodyLines);
  }
  if (sectionType === "checkbox_yesno") {
    return _extractYesNoItems(bodyLines);
  }
  if (sectionType === "scale") {
    return _extractScaleItems(bodyLines);
  }
  return [];
}

function _startPattern(label: string): string {
  const letter = label.match(/section\s+([a-z])/i)?.[1];
  if (letter) return `(?i)section\\s+${letter.toLowerCase()}:`;
  const first = label.split(/\s+/).slice(0, 3).join("\\s+");
  return `(?i)${first}`;
}

// -- Public API --------------------------------------------------------------

/**
 * Analyse ``text`` and return proposed :FormSchema sections.
 * All proposed section types and items can be overridden by the clinician
 * in the FormSchemaAnnotator UI before saving.
 */
export function detectSections(text: string): FormSchemaSection[] {
  if (!text.trim()) return [];

  const lines = normalizeFormText(text).split("\n");
  const breakpoints: Array<{ idx: number; label: string }> = [];

  lines.forEach((ln, idx) => {
    const stripped = ln.replace(/^\s*[#]+\s*/, "").trim();
    if (SECTION_HEADER.test(stripped)) {
      breakpoints.push({ idx, label: stripped });
    } else if (NAMED_HEADER.test(stripped)) {
      breakpoints.push({ idx, label: stripped });
    }
  });

  if (breakpoints.length === 0) return [];

  const sections: FormSchemaSection[] = [];
  for (let i = 0; i < breakpoints.length; i++) {
    const { idx, label } = breakpoints[i];
    const nextIdx =
      i + 1 < breakpoints.length ? breakpoints[i + 1].idx : lines.length;
    const bodyLines = lines
      .slice(idx + 1, nextIdx)
      .filter((ln) => ln.trim().length > 0);

    const isAdmin = ADMIN_HEADER.test(label);
    const sectionType: SectionType = isAdmin
      ? "admin"
      : _classifyLines(bodyLines);

    const items = _buildItems(sectionType, bodyLines);

    const sectionLetter = label.match(/section\s+([a-z])/i)?.[1] ?? String(i);
    sections.push({
      section_id: sectionLetter.toUpperCase(),
      section_type: sectionType,
      label,
      start_pattern: _startPattern(label),
      items,
    });
  }

  return sections;
}
