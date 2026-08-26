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

export type CompletenessLogicGroup = {
  name: string;
  kind: string;
  required: boolean;
  min_count?: number;
  semantic_categories: string[];
  concept_ids: number[];
  members?: CompletenessLogicGroup[];
  if_group?: CompletenessLogicGroup | null;
  then_group?: CompletenessLogicGroup | null;
};

export function emptyCompletenessGroup(kind = "mandatory"): CompletenessLogicGroup {
  return {
    name: "New rule",
    kind,
    required: kind !== "optional",
    semantic_categories: [],
    concept_ids: [],
    members: kind === "one_of" || kind === "n_of" ? [
      { name: "Option 1", kind: "optional", required: false, semantic_categories: [], concept_ids: [] },
      { name: "Option 2", kind: "optional", required: false, semantic_categories: [], concept_ids: [] },
    ] : [],
  };
}

export async function saveTaughtForm(args: {
  fingerprint: string;
  name: string;
  sections: FormSchemaSection[];
  organizationId: string;
  serviceId: string;
  completenessGroups: CompletenessLogicGroup[];
}): Promise<void> {
  const res = await fetch(`/api/form-schemas/${args.fingerprint}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({
      form_name: args.name,
      sections: args.sections,
      saved_by: "validation_lab",
      organization_id: args.organizationId,
      service_id: args.serviceId,
      completeness_groups: args.completenessGroups,
    }),
  });
  if (!res.ok) {
    throw new Error("Could not save the form schema. Try again.");
  }
}
