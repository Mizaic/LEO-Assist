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

/**
 * True when there are no usable clinical sections.
 *
 * A schema is incomplete when:
 * - It is empty, or
 * - Every section is an admin/template_noise skip type, or
 * - Every clinical section has an empty label (the LLM returned the
 *   right structure but omitted the content strings).
 */
export function isIncompleteSchema(
  sections: Array<{ section_type: string; label?: string }>,
): boolean {
  if (!sections.length) return true;
  const clinical = sections.filter((s) => !SKIP_TYPES.has(s.section_type));
  if (!clinical.length) return true;
  return clinical.every((s) => !(s.label ?? "").trim());
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

/** Drop blank items and fill start_pattern before PUT /form-schemas. */
export function prepareSectionsForSave(
  sections: FormSchemaSection[],
): FormSchemaSection[] {
  return sections
    .map((section) => {
      const label = (section.label ?? "").trim();
      const start =
        (section.start_pattern ?? "").trim() || label || section.section_id;
      const items = section.items
        .map((item) => ({
          ...item,
          pattern: (item.pattern ?? "").trim(),
          entity_text: (item.entity_text ?? "").trim(),
        }))
        .filter((item) => item.pattern && item.entity_text);
      return { ...section, start_pattern: start, items };
    })
    .filter((section) => section.start_pattern.trim());
}

const HEX_FINGERPRINT = /^[a-f0-9]{16}$/i;

/** Prefer content hash; never use document-quality match id "unknown". */
export function resolveTeachFingerprint(raw: Record<string, unknown>): string {
  const fromApi = String(raw.form_fingerprint ?? "").trim();
  if (fromApi && fromApi !== "unknown") {
    return fromApi;
  }
  const quality = (raw.document_quality ?? {}) as {
    form_fingerprint_id?: string;
  };
  const legacy = String(quality.form_fingerprint_id ?? "").trim();
  if (legacy && legacy !== "unknown" && HEX_FINGERPRINT.test(legacy)) {
    return legacy;
  }
  return fromApi;
}

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
  const fingerprint = args.fingerprint.trim();
  if (!fingerprint || fingerprint === "unknown") {
    throw new Error(
      "We could not identify this form. Reload the letter and try again.",
    );
  }
  const sections = prepareSectionsForSave(args.sections);
  if (!sections.length) {
    throw new Error("Add at least one section with a start pattern before saving.");
  }
  const res = await fetch(`/api/form-schemas/${fingerprint}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({
      form_name: args.name,
      sections,
      saved_by: "validation_lab",
      organization_id: args.organizationId,
      service_id: args.serviceId,
      completeness_groups: args.completenessGroups,
    }),
  });
  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    throw new Error(detail || "Could not save the form schema. Try again.");
  }
}

async function readApiErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string | Array<{ msg?: string }> };
    const detail = body.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      const msg = detail.map((row) => row.msg ?? "").filter(Boolean).join("; ");
      if (msg) return msg;
    }
  } catch {
    /* ignore parse errors */
  }
  return "";
}
