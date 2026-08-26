/**
 * Helpers for Teach this form -- empty sections and detect errors.
 *
 * Atlas trace: DI-5C9CA57B
 */
import {
  detectSections,
  type FormSchemaSection,
} from "./formSchemaDetector";

export function emptySection(index: number): FormSchemaSection {
  return {
    section_id: `S${index + 1}`,
    section_type: "checkbox_single",
    label: "New section",
    start_pattern: "",
    items: [],
  };
}

export function detectFailureMessage(status: number): string {
  if (status === 401 || status === 403) {
    return "You are not allowed to auto-detect this form. Add a section to teach it.";
  }
  if (status >= 500) {
    return "LEO could not read the form just now. Add a section, or try again.";
  }
  return "LEO could not detect sections automatically. Add a section to teach this form.";
}

export function localDetectOrEmpty(sourceText: string): FormSchemaSection[] {
  return detectSections(sourceText);
}

const SKIP_TYPES = new Set(["admin", "template_noise"]);

export function isIncompleteSchema(
  sections: Array<{ section_type: string }>,
): boolean {
  if (!sections.length) return true;
  return sections.every((section) => SKIP_TYPES.has(section.section_type));
}
