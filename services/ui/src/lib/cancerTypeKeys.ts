/**
 * Shared cancer type key utilities for the audit UI.
 *
 * The live patient graph stores cancer_type values in varied formats
 * (e.g. "bowel", "Upper GI", "head and neck"). Benchmark metric_ids use
 * lowercase snake_case canonical keys. This module centralises the mapping
 * so both the bullet chart and the accordion use identical normalisation.
 *
 * Published fallback early-stage rates (% at stage 1 or 2) are national
 * England figures from NDRS/NCRA 2018-2019:
 *   - NHS Digital Cancer Registration Statistics 2019
 *   - NHS England NDRS Stage at Diagnosis data hub (2018)
 *   - Barclay et al. (2021) Br J Cancer 124:1320-1329 (2015 England data)
 *   - NCDA 2018 national tables (Table 1, NCIN)
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
/** Cancer types excluded from all visualisations (no meaningful stage data). */
export const EXCLUDED_CANCER_TYPES = new Set(["unknown", "non_site_specific"]);

/**
 * Normalise a raw cancer_type value from the patient graph to the canonical
 * benchmark metric_id fragment (lowercase snake_case).
 */
export function normaliseLiveKey(raw: string): string {
  const s = raw.toLowerCase().trim().replace(/\s+/g, "_");
  const REMAP: Record<string, string> = {
    bowel:                    "colorectal",
    "colorectal_/_bowel":     "colorectal",
    lower_gi:                 "colorectal",
    colo_rectal:              "colorectal",
    "bowel_(colorectal)":     "colorectal",
    upper_gi:                 "upper_gi",
    upper_gastrointestinal:   "upper_gi",
    head_and_neck:            "head_and_neck",
    "head_&_neck":            "head_and_neck",
    "h&n":                    "head_and_neck",
    skin:                     "melanoma",
    cns:                      "brain",
    nervous_system:           "brain",
    gynaecological:           "gynaecological",
    gynaecology:              "gynaecological",
    haematological:           "haematological",
    haematology:              "haematological",
    urological:               "urological",
    urology:                  "urological",
  };
  return REMAP[s] ?? s;
}

/**
 * Human-readable labels for canonical cancer type keys.
 * Falls back to title-casing the key with underscores replaced by spaces.
 */
export function cancerTypeLabel(key: string): string {
  const LABELS: Record<string, string> = {
    breast:         "Breast",
    colorectal:     "Colorectal",
    lung:           "Lung",
    prostate:       "Prostate",
    melanoma:       "Melanoma",
    bladder:        "Bladder",
    renal:          "Renal",
    ovarian:        "Ovarian",
    endometrial:    "Endometrial",
    cervical:       "Cervical",
    testicular:     "Testicular",
    thyroid:        "Thyroid",
    oesophageal:    "Oesophageal",
    stomach:        "Stomach",
    liver:          "Liver",
    pancreatic:     "Pancreatic",
    head_and_neck:  "Head and Neck",
    upper_gi:       "Upper GI",
    brain:          "Brain / CNS",
    leukaemia:      "Leukaemia",
    lymphoma:       "Lymphoma",
    myeloma:        "Myeloma",
    haematological: "Haematological",
  };
  return LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Fallback national 2018/2019 early-stage rates (% at stage 1 or 2).
 * Used when the KG benchmark has no entry for a given cancer type.
 * Null = staging convention does not apply (haematological, brain).
 */
export const FALLBACK_NATIONAL_2019: Record<string, number | null> = {
  breast:         76,
  colorectal:     39,
  lung:           26,
  prostate:       50,
  melanoma:       91,
  bladder:        72,
  renal:          57,
  ovarian:        28,
  endometrial:    79,
  cervical:       82,
  testicular:     95,
  thyroid:        70,
  oesophageal:    24,
  stomach:        33,
  liver:          15,
  pancreatic:     18,
  head_and_neck:  50,
  upper_gi:       24,
  brain:          null,
  leukaemia:      null,
  lymphoma:       null,
  myeloma:        null,
  haematological: null,
};

/** Resolve the 2019 national early-stage % for a canonical key. Prefers KG benchmark. */
export function resolveBaseline2019(
  key: string,
  bm: Record<string, { national?: number | null }> | null | undefined,
): number | null {
  const bmVal = bm?.[`cancer_stage.by_cancer_type.${key}.early_stage_pct`]?.national ?? null;
  if (bmVal != null) return bmVal;
  return key in FALLBACK_NATIONAL_2019 ? FALLBACK_NATIONAL_2019[key] : null;
}
