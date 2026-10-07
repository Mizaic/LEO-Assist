/**
 * Helpers for Teach this form -- empty sections and detect errors.
 *
 * Atlas trace: DI-5C9CA57B
 */
import {
  coerceSectionType,
  detectSections,
  type FormSchemaItem,
  type FormSchemaSection,
} from "./formSchemaDetector";

/**
 * Repair section types on sections that came from the server.
 *
 * A saved schema or an LLM detect response is JSON, not a typed value.
 * An unrecognised type would leave the editor dropdown blank and would be
 * rejected by the API on save, so fix it as it comes in.
 */
export function coerceLoadedSections(
  sections: FormSchemaSection[],
): FormSchemaSection[] {
  return sections.map((section) => ({
    ...section,
    section_type: coerceSectionType(section.section_type),
  }));
}

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

function sectionHasTaughtContent(
  section: { section_type: string; label?: string; start_pattern?: string; items?: FormSchemaItem[] },
): boolean {
  if ((section.label ?? "").trim()) return true;
  if ((section.start_pattern ?? "").trim()) return true;
  for (const item of section.items ?? []) {
    if ((item.pattern ?? "").trim() || (item.entity_text ?? "").trim()) {
      return true;
    }
    if ((item.procedure_snomed ?? "").trim()) return true;
    if (
      (item.analytes ?? []).some(
        (a) => (a.label ?? "").trim() || (a.snomed_code ?? "").trim(),
      )
    ) {
      return true;
    }
  }
  return false;
}

/**
 * True when there are no usable clinical sections.
 *
 * A schema is incomplete when:
 * - It is empty, or
 * - Every section is an admin/template_noise skip type, or
 * - Every clinical section has no label and no taught items (the LLM
 *   returned the right structure but omitted the content strings).
 */
export function isIncompleteSchema(
  sections: Array<{ section_type: string; label?: string; start_pattern?: string; items?: FormSchemaItem[] }>,
): boolean {
  if (!sections.length) return true;
  const clinical = sections.filter((s) => !SKIP_TYPES.has(s.section_type));
  if (!clinical.length) return true;
  return clinical.every((s) => !sectionHasTaughtContent(s));
}

export function savedSchemaBlocksAutoDetect(
  sections: Array<{ section_type: string; label?: string; start_pattern?: string; items?: FormSchemaItem[] }>,
): boolean {
  if (!sections.length) return false;
  if (!isIncompleteSchema(sections)) return true;
  return sections.some(
    (section) =>
      !SKIP_TYPES.has(section.section_type) && sectionHasTaughtContent(section),
  );
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
        .map((item) => normalizeItemForSave(item, section.section_type))
        .filter((item): item is FormSchemaItem => item !== null);
      return { ...section, start_pattern: start, items };
    })
    .filter((section) => section.start_pattern.trim());
}

function orderedTestsItemHasContent(item: FormSchemaItem): boolean {
  if ((item.pattern ?? "").trim() || (item.procedure_snomed ?? "").trim()) {
    return true;
  }
  return (item.analytes ?? []).some(
    (a) => (a.label ?? "").trim() || (a.snomed_code ?? "").trim(),
  );
}

function normalizeItemForSave(
  item: FormSchemaItem,
  sectionType: FormSchemaSection["section_type"],
): FormSchemaItem | null {
  const pattern = (item.pattern ?? "").trim();
  let entityText = (item.entity_text ?? "").trim();
  if (sectionType === "ordered_tests") {
    if (!orderedTestsItemHasContent(item)) return null;
    if (!entityText) {
      entityText =
        (item.procedure_display ?? "").trim() || pattern;
    }
    return { ...item, pattern, entity_text: entityText };
  }
  if (!pattern || !entityText) return null;
  return { ...item, pattern, entity_text: entityText };
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

export type TeachScopeIds = {
  organizationId?: string;
  serviceId?: string;
};

export type LoadedTeachSchema = {
  form_name: string;
  fingerprint?: string;
  sections: FormSchemaSection[];
};

const FETCH_HDRS = { "X-Requested-With": "XMLHttpRequest" };

export async function loadTaughtLibrarySchema(
  fingerprint: string,
  scope?: TeachScopeIds,
): Promise<LoadedTeachSchema | null> {
  const byScope = await loadSchemaByOrgService(scope);
  if (byScope && savedSchemaBlocksAutoDetect(byScope.sections)) {
    return byScope;
  }
  const byHash = await loadSchemaByFingerprint(fingerprint, scope);
  if (byHash && savedSchemaBlocksAutoDetect(byHash.sections)) {
    return byHash;
  }
  return byScope ?? byHash;
}

async function loadSchemaByOrgService(
  scope?: TeachScopeIds,
): Promise<LoadedTeachSchema | null> {
  const org = (scope?.organizationId ?? "").trim();
  const service = (scope?.serviceId ?? "").trim();
  if (!org || !service) return null;
  try {
    const params = new URLSearchParams({
      organization_id: org,
      service_id: service,
    });
    const listRes = await fetch(`/api/form-schemas?${params.toString()}`, {
      credentials: "include",
      headers: FETCH_HDRS,
    });
    if (!listRes.ok) return null;
    const list = (await listRes.json()) as {
      schemas?: Array<{
        fingerprint?: string;
        organization_id?: string;
        service_id?: string;
      }>;
    };
    const match = (list.schemas ?? []).find(
      (row) =>
        (row.organization_id || "") === org && (row.service_id || "") === service,
    );
    const libraryFp = (match?.fingerprint || "").trim();
    if (!libraryFp) return null;
    return loadSchemaByFingerprint(libraryFp);
  } catch {
    return null;
  }
}

async function loadSchemaByFingerprint(
  fingerprint: string,
  scope?: TeachScopeIds,
): Promise<LoadedTeachSchema | null> {
  const fp = fingerprint.trim();
  if (!fp || fp === "unknown") return null;
  try {
    const params = new URLSearchParams();
    if (scope?.organizationId) params.set("organization_id", scope.organizationId);
    if (scope?.serviceId) params.set("service_id", scope.serviceId);
    const query = params.toString();
    const url = `/api/form-schemas/${encodeURIComponent(fp)}${query ? `?${query}` : ""}`;
    const existing = await fetch(url, {
      credentials: "include",
      headers: FETCH_HDRS,
    });
    if (!existing.ok) return null;
    const payload = (await existing.json()) as { schema: LoadedTeachSchema | null };
    if (!payload.schema) return null;
    return {
      ...payload.schema,
      sections: coerceLoadedSections(payload.schema.sections ?? []),
    };
  } catch {
    return null;
  }
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
  organizationName?: string;
  serviceName?: string;
  completenessGroups: CompletenessLogicGroup[];
  sourceText: string;
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
      organization_name: args.organizationName ?? "",
      service_name: args.serviceName ?? "",
      completeness_groups: args.completenessGroups,
      source_text: args.sourceText,
    }),
  });
  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    throw new Error(detail || "Could not save the form schema. Try again.");
  }
}

export async function readApiErrorDetail(res: Response): Promise<string> {
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
