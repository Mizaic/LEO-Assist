/**
 * Loads the standard NHS blood panel preset for the form teacher.
 *
 * The blood results table on an NHS urgent suspected cancer referral is
 * the same across trusts, so the codes come from the server rather than
 * being typed in by hand. The user can delete any row afterwards.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

import type { AnalyteEntry, FormSchemaItem } from "./formSchemaDetector";

const PRESET_URL = "/api/form-schemas/blood-panel-presets";

export const PRESET_LOAD_ERROR =
  "We could not load the standard blood panel. Try again.";

interface PresetAnalyteResponse {
  label?: string;
  snomed_code?: string;
  display?: string;
}

interface PresetBatteryResponse {
  pattern?: string;
  entity_text?: string;
  semantic_tag?: string;
  assertion?: string;
  procedure_snomed?: string;
  procedure_display?: string;
  analytes?: PresetAnalyteResponse[];
  value_placeholder?: string;
}

interface PresetResponse {
  batteries?: PresetBatteryResponse[];
  needs_clinical_review?: Record<string, string>;
}

function toAnalyte(raw: PresetAnalyteResponse): AnalyteEntry {
  return {
    label: raw.label ?? "",
    snomed_code: raw.snomed_code ?? "",
    display: raw.display ?? "",
  };
}

function toItem(raw: PresetBatteryResponse): FormSchemaItem {
  return {
    pattern: raw.pattern ?? "",
    entity_text: raw.entity_text ?? "",
    semantic_tag: raw.semantic_tag ?? "procedure",
    assertion: raw.assertion ?? "present",
    procedure_snomed: raw.procedure_snomed ?? "",
    procedure_display: raw.procedure_display ?? "",
    analytes: (raw.analytes ?? []).map(toAnalyte),
    value_placeholder: raw.value_placeholder ?? "",
  };
}

export async function fetchBloodPanelPreset(): Promise<FormSchemaItem[]> {
  const res = await fetch(PRESET_URL, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) throw new Error(PRESET_LOAD_ERROR);
  const payload = (await res.json()) as PresetResponse;
  return (payload.batteries ?? []).map(toItem);
}

function batteryKey(pattern: string): string {
  return pattern.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function isBlankRow(item: FormSchemaItem): boolean {
  return (
    !item.pattern.trim() &&
    !item.entity_text.trim() &&
    !(item.procedure_snomed ?? "").trim() &&
    !(item.analytes ?? []).length
  );
}

/**
 * Append preset batteries the section does not already have.
 *
 * Rows the user has already typed are kept exactly as they are, so a
 * second click cannot overwrite or duplicate their work. Empty
 * placeholder rows are dropped.
 */
export function mergePresetBatteries(
  existing: FormSchemaItem[],
  preset: FormSchemaItem[],
): FormSchemaItem[] {
  const kept = existing.filter((item) => !isBlankRow(item));
  const seen = new Set(kept.map((item) => batteryKey(item.pattern)));
  const added = preset.filter((item) => !seen.has(batteryKey(item.pattern)));
  return [...kept, ...added];
}
