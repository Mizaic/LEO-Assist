/**
 * Form-schema chip helpers for Validation Lab INPUT KEYS.
 *
 * Atlas trace: DI-FE423B8D / DO-158BE606
 */

export const FORM_SCHEMA_CHIP_KEYS = new Set([
  "form_schema_fingerprint",
  "form_schema",
]);

export function formSchemaViewHref(fingerprint: unknown): string {
  const fp = String(fingerprint ?? "").trim();
  if (!fp || fp === "none") {
    return "/admin/knowledge?tab=form-templates";
  }
  return `/admin/knowledge?tab=form-templates&fingerprint=${encodeURIComponent(fp)}`;
}

export function formSchemaChipLabel(name: string, value: unknown): string {
  const fp = String(value ?? "").trim() || "none";
  if (name === "form_schema_fingerprint" || name === "form_schema") {
    return `${name}: ${fp}`;
  }
  return name;
}
