/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387
 *   DO: DO-AA74E9A6
 *   VT: VT-5632FA0D
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-C21AE387")
 *
 * Unit options for observation thresholds. Prefer LabResultConfig
 * (Admin > Knowledge > Results/Labs / libs/units converter). Fallback
 * is the unique UCUM strings from OBSERVABLE_UNIT_REGISTRY.
 */

export interface LabUnitSource {
  canonical_unit?: string | null;
  conversions?: Array<{ unit?: string | null }> | null;
}

/** Unique units from libs/units/observable_units.py (seed / fallback). */
export const FALLBACK_OBSERVABLE_UNITS: readonly string[] = [
  "%",
  "% DCCT",
  "/nL",
  "10*3/uL",
  "10*9/L",
  "10^3/uL",
  "10^9/L",
  "IU/L",
  "K/uL",
  "U/L",
  "[lb_av]",
  "cm",
  "g",
  "g/100mL",
  "g/L",
  "g/dL",
  "iu/L",
  "kg",
  "kg/(m^2)",
  "kg/m2",
  "kg/m^2",
  "lb",
  "m",
  "mL/min/1.73 m2",
  "mL/min/1.73m2",
  "mL/min/{1.73_m2}",
  "mcg/L",
  "mg/dL",
  "microgram/g",
  "micromol/L",
  "ml/min/1.73m2",
  "mm",
  "mm Hg",
  "mmHg",
  "mm[Hg]",
  "mmol/L",
  "mmol/mol",
  "ng/mL",
  "uMol/L",
  "ug/L",
  "ug/g",
  "umol/L",
  "x10*9/L",
  "x10^9/L",
];

function cleanUnit(raw: string | null | undefined): string | null {
  const trimmed = String(raw ?? "").trim();
  return trimmed ? trimmed : null;
}

/** Canonical unit plus accepted conversion aliases, de-duplicated. */
export function unitsFromLabConfig(source: LabUnitSource | null | undefined): string[] {
  if (!source) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  const push = (raw: string | null | undefined) => {
    const unit = cleanUnit(raw);
    if (!unit || seen.has(unit)) return;
    seen.add(unit);
    out.push(unit);
  };
  push(source.canonical_unit);
  for (const row of source.conversions ?? []) {
    push(row?.unit);
  }
  return out;
}

/** Options for a unit Select: lab config when present, else registry fallback. */
export function unitOptionsForObservable(
  source: LabUnitSource | null | undefined,
  currentUnit?: string | null,
): string[] {
  const fromConfig = unitsFromLabConfig(source);
  const base = fromConfig.length > 0 ? fromConfig : [...FALLBACK_OBSERVABLE_UNITS];
  const current = cleanUnit(currentUnit);
  if (current && !base.includes(current)) {
    return [current, ...base];
  }
  return base;
}

export function preferredUnit(source: LabUnitSource | null | undefined): string {
  return cleanUnit(source?.canonical_unit) ?? "";
}
