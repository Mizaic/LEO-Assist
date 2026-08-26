/**
 * Match Teach this form sections to letter headings and checkbox labels.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */

import type { FormSchemaSection } from "./formSchemaDetector";

export interface LetterSectionRegion {
  regionId: string;
  label: string;
  itemPatterns: string[];
}

export function regionsFromSections(
  sections: FormSchemaSection[],
): LetterSectionRegion[] {
  return sections.map((section) => ({
    regionId: section.section_id,
    label: section.label,
    itemPatterns: section.items
      .map((item) => item.pattern.trim())
      .filter(Boolean),
  }));
}

export function matchSectionFromLetterText(
  sections: FormSchemaSection[],
  rawText: string,
): FormSchemaSection | undefined {
  const text = rawText.trim();
  if (!text || sections.length === 0) return undefined;
  return (
    matchBySectionId(sections, text) ||
    matchByLabel(sections, text) ||
    matchByItemPattern(sections, text)
  );
}

export function regionHitForText(
  regions: LetterSectionRegion[],
  text: string,
): { regionId: string; primary: boolean } | undefined {
  const sections = regions.map(regionToSection);
  const match = matchSectionFromLetterText(sections, text);
  if (!match) return undefined;
  return {
    regionId: match.section_id,
    primary: isPrimaryLetterMatch(text, match),
  };
}

export function isPrimaryLetterMatch(
  text: string,
  section: FormSchemaSection,
): boolean {
  const lower = text.toLowerCase();
  const label = section.label.trim().toLowerCase();
  if (label && lower.includes(label)) return true;
  return lower.includes(`section ${section.section_id.toLowerCase()}`);
}

/**
 * Extract the leading letter prefix from a row identifier such as "B1" or "B1.".
 * Returns the alpha-only prefix (e.g. "b") or null when not matched.
 */
function alphaPrefix(text: string): string | null {
  const m = text.match(/^([A-Za-z]+)\d+[.\s]/);
  return m ? (m[1] ?? "").toLowerCase() : null;
}

/**
 * Strip form-field noise from a raw letter selection so it becomes a
 * clean entity label.
 * "B1. Lesion site (please tick)" -> "Lesion site"
 */
export function cleanLetterSelectionText(raw: string): string {
  let text = raw.trim();
  // Strip leading row identifier e.g. "B1. " or "A2 "
  text = text.replace(/^[A-Za-z]+\d+[.\s]\s*/, "");
  // Strip leading single letter + dot e.g. "A. " used in some forms
  text = text.replace(/^[A-Za-z]\.\s+/, "");
  // Strip trailing parenthetical form instructions
  text = text.replace(/\s*\(.*?\)\s*$/, "");
  return text.trim();
}

function matchBySectionId(
  sections: FormSchemaSection[],
  text: string,
): FormSchemaSection | undefined {
  const byId = new Map(
    sections.map((section) => [section.section_id.toLowerCase(), section]),
  );
  // "Section B" style headings
  const headingHits = text.matchAll(/section\s+([a-z0-9]+)\b/gi);
  for (const hit of headingHits) {
    const found = byId.get((hit[1] ?? "").toLowerCase());
    if (found) return found;
  }
  // Row identifier prefix: "B1. Lesion" -> try "b" -> Section B
  const prefix = alphaPrefix(text);
  if (prefix) {
    const found = byId.get(prefix);
    if (found) return found;
  }
  return byId.get(text.trim().toLowerCase());
}

function matchByLabel(
  sections: FormSchemaSection[],
  text: string,
): FormSchemaSection | undefined {
  const lower = text.toLowerCase();
  return sections.find((section) => {
    const label = section.label.trim().toLowerCase();
    if (!label) return false;
    return label === lower || label.includes(lower) || lower.includes(label);
  });
}

function matchByItemPattern(
  sections: FormSchemaSection[],
  text: string,
): FormSchemaSection | undefined {
  const lower = text.toLowerCase();
  let best: { section: FormSchemaSection; length: number } | undefined;
  for (const section of sections) {
    for (const item of section.items) {
      const pattern = item.pattern.trim().toLowerCase();
      if (!pattern) continue;
      if (lower !== pattern && !lower.includes(pattern)) continue;
      if (!best || pattern.length > best.length) {
        best = { section, length: pattern.length };
      }
    }
  }
  return best?.section;
}

function regionToSection(region: LetterSectionRegion): FormSchemaSection {
  return {
    section_id: region.regionId,
    section_type: "free_text",
    label: region.label,
    start_pattern: "",
    items: region.itemPatterns.map((pattern) => ({
      pattern,
      entity_text: pattern,
      semantic_tag: "",
      assertion: "present",
    })),
  };
}
