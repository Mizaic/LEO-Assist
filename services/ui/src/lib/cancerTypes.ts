/**
 * Canonical NCDA cancer-type vocabulary (DI-5CAC6D73).
 *
 * MIRROR of libs/oncology/cancer_types.py -- keep in sync. The contract
 * test tests/contracts/test_cancer_type_vocabulary.py parses this file
 * and fails the build if any value drifts from the Python source of
 * truth.
 *
 * Every UI component that compares, filters, orders or labels a cancer
 * type MUST import the constants and helpers from this file. Never
 * inline a string literal like "Breast" or "Colorectal" in a chart
 * config or a switch statement.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export const CANCER_TYPE_BLADDER = "Bladder";
export const CANCER_TYPE_BRAIN = "Brain";
export const CANCER_TYPE_BREAST = "Breast";
export const CANCER_TYPE_CERVICAL = "Cervical";
export const CANCER_TYPE_COLORECTAL = "Colorectal";
export const CANCER_TYPE_ENDOMETRIAL = "Endometrial";
export const CANCER_TYPE_GALLBLADDER = "Gallbladder";
export const CANCER_TYPE_LARYNGEAL = "Laryngeal";
export const CANCER_TYPE_LEUKAEMIA = "Leukaemia";
export const CANCER_TYPE_LIVER = "Liver";
export const CANCER_TYPE_LUNG = "Lung";
export const CANCER_TYPE_LYMPHOMA = "Lymphoma";
export const CANCER_TYPE_MELANOMA = "Melanoma";
export const CANCER_TYPE_MESOTHELIOMA = "Mesothelioma";
export const CANCER_TYPE_MYELOMA = "Myeloma";
export const CANCER_TYPE_OESOPHAGEAL = "Oesophageal";
export const CANCER_TYPE_OROPHARYNGEAL = "Oropharyngeal";
export const CANCER_TYPE_OVARIAN = "Ovarian";
export const CANCER_TYPE_PANCREATIC = "Pancreatic";
export const CANCER_TYPE_PROSTATE = "Prostate";
export const CANCER_TYPE_RENAL = "Renal";
export const CANCER_TYPE_SARCOMA = "Sarcoma";
export const CANCER_TYPE_SMALL_INTESTINE = "Small Intestine";
export const CANCER_TYPE_STOMACH = "Stomach";
export const CANCER_TYPE_TESTICULAR = "Testicular";
export const CANCER_TYPE_THYROID = "Thyroid";
export const CANCER_TYPE_VULVAL = "Vulval";
export const CANCER_TYPE_OTHER = "Other";
export const CANCER_TYPE_UNKNOWN_PRIMARY = "Unknown Primary";
export const CANCER_TYPE_NO_INFORMATION = "No Information";

/** Display order matching the NCDA data-entry form. */
export const CANCER_TYPE_OPTIONS: readonly string[] = [
  CANCER_TYPE_BLADDER,
  CANCER_TYPE_BRAIN,
  CANCER_TYPE_BREAST,
  CANCER_TYPE_CERVICAL,
  CANCER_TYPE_COLORECTAL,
  CANCER_TYPE_ENDOMETRIAL,
  CANCER_TYPE_GALLBLADDER,
  CANCER_TYPE_LARYNGEAL,
  CANCER_TYPE_LEUKAEMIA,
  CANCER_TYPE_LIVER,
  CANCER_TYPE_LUNG,
  CANCER_TYPE_LYMPHOMA,
  CANCER_TYPE_MELANOMA,
  CANCER_TYPE_MESOTHELIOMA,
  CANCER_TYPE_MYELOMA,
  CANCER_TYPE_OESOPHAGEAL,
  CANCER_TYPE_OROPHARYNGEAL,
  CANCER_TYPE_OVARIAN,
  CANCER_TYPE_PANCREATIC,
  CANCER_TYPE_PROSTATE,
  CANCER_TYPE_RENAL,
  CANCER_TYPE_SARCOMA,
  CANCER_TYPE_SMALL_INTESTINE,
  CANCER_TYPE_STOMACH,
  CANCER_TYPE_TESTICULAR,
  CANCER_TYPE_THYROID,
  CANCER_TYPE_VULVAL,
  CANCER_TYPE_OTHER,
  CANCER_TYPE_UNKNOWN_PRIMARY,
  CANCER_TYPE_NO_INFORMATION,
];

export const CANCER_TYPE_SET: ReadonlySet<string> = new Set(CANCER_TYPE_OPTIONS);

const CANCER_TYPE_ORDER: ReadonlyMap<string, number> = new Map(
  CANCER_TYPE_OPTIONS.map((value, index) => [value, index]),
);

/**
 * Raw -> canonical map. Keys are lower-cased, whitespace-stripped forms
 * observed on the live graph (mirrors `_RAW_TO_CANONICAL` in
 * libs/oncology/cancer_types.py).
 */
const RAW_TO_CANONICAL: Readonly<Record<string, string>> = {
  bladder: CANCER_TYPE_BLADDER,
  brain: CANCER_TYPE_BRAIN,
  breast: CANCER_TYPE_BREAST,
  cervix: CANCER_TYPE_CERVICAL,
  cervical: CANCER_TYPE_CERVICAL,
  colorectal: CANCER_TYPE_COLORECTAL,
  endometrial: CANCER_TYPE_ENDOMETRIAL,
  endometrium: CANCER_TYPE_ENDOMETRIAL,
  gallbladder: CANCER_TYPE_GALLBLADDER,
  larynx: CANCER_TYPE_LARYNGEAL,
  laryngeal: CANCER_TYPE_LARYNGEAL,
  leukaemia: CANCER_TYPE_LEUKAEMIA,
  leukemia: CANCER_TYPE_LEUKAEMIA,
  liver: CANCER_TYPE_LIVER,
  lung: CANCER_TYPE_LUNG,
  lymphoma: CANCER_TYPE_LYMPHOMA,
  melanoma: CANCER_TYPE_MELANOMA,
  mesothelioma: CANCER_TYPE_MESOTHELIOMA,
  myeloma: CANCER_TYPE_MYELOMA,
  oesophageal: CANCER_TYPE_OESOPHAGEAL,
  oesophagus: CANCER_TYPE_OESOPHAGEAL,
  oropharynx: CANCER_TYPE_OROPHARYNGEAL,
  oropharyngeal: CANCER_TYPE_OROPHARYNGEAL,
  ovarian: CANCER_TYPE_OVARIAN,
  ovary: CANCER_TYPE_OVARIAN,
  pancreas: CANCER_TYPE_PANCREATIC,
  pancreatic: CANCER_TYPE_PANCREATIC,
  prostate: CANCER_TYPE_PROSTATE,
  kidney: CANCER_TYPE_RENAL,
  renal: CANCER_TYPE_RENAL,
  sarcoma: CANCER_TYPE_SARCOMA,
  "small intestine": CANCER_TYPE_SMALL_INTESTINE,
  "small bowel": CANCER_TYPE_SMALL_INTESTINE,
  stomach: CANCER_TYPE_STOMACH,
  testicular: CANCER_TYPE_TESTICULAR,
  testis: CANCER_TYPE_TESTICULAR,
  thyroid: CANCER_TYPE_THYROID,
  vulval: CANCER_TYPE_VULVAL,
  vulva: CANCER_TYPE_VULVAL,
  skin: CANCER_TYPE_MELANOMA,
  "head and neck": CANCER_TYPE_OROPHARYNGEAL,
  "head & neck": CANCER_TYPE_OROPHARYNGEAL,
  "thyroid/neck (non-site-specific pathway)": CANCER_TYPE_THYROID,
  anal: CANCER_TYPE_COLORECTAL,
  "upper gi": CANCER_TYPE_OTHER,
  "upper gastrointestinal": CANCER_TYPE_OTHER,
  "gastric/oesophageal": CANCER_TYPE_OESOPHAGEAL,
  "stomach/oesophagus (junctional)": CANCER_TYPE_OESOPHAGEAL,
  urological: CANCER_TYPE_OTHER,
  "urinary bladder / prostate": CANCER_TYPE_PROSTATE,
  gynaecological: CANCER_TYPE_OTHER,
  "gynaecological (cervix)": CANCER_TYPE_CERVICAL,
  haematology: CANCER_TYPE_LYMPHOMA,
  "haematology (lymphoma)": CANCER_TYPE_LYMPHOMA,
  lymphoid: CANCER_TYPE_LYMPHOMA,
  "lymph node / mediastinal mass (pediatric)": CANCER_TYPE_LYMPHOMA,
  "salivary gland": CANCER_TYPE_OTHER,
  cardiac: CANCER_TYPE_OTHER,
  unknown: CANCER_TYPE_UNKNOWN_PRIMARY,
  "unknown primary": CANCER_TYPE_UNKNOWN_PRIMARY,
  "no information": CANCER_TYPE_NO_INFORMATION,
  other: CANCER_TYPE_OTHER,
  "": CANCER_TYPE_NO_INFORMATION,
};

/**
 * Coerce any raw cancer-type / suspected-site string to a canonical value.
 *
 * Returns `No Information` for `null`, `undefined` or empty input,
 * a matching canonical value for known synonyms, and `Other` for any
 * unrecognised non-empty value. Idempotent on already-canonical input.
 */
export function normaliseCancerType(raw: string | null | undefined): string {
  if (raw == null) return CANCER_TYPE_NO_INFORMATION;
  const key = String(raw).trim().toLowerCase();
  if (!key) return CANCER_TYPE_NO_INFORMATION;
  if (CANCER_TYPE_SET.has(raw)) return raw;
  const canonical = RAW_TO_CANONICAL[key];
  if (canonical) return canonical;
  return CANCER_TYPE_OTHER;
}

/**
 * Pretty label for a canonical cancer type. Currently the canonical
 * value is itself the display label; the indirection exists so that
 * the UI never special-cases the string in components.
 */
export function getCancerTypeLabel(canonical: string): string {
  return CANCER_TYPE_SET.has(canonical) ? canonical : CANCER_TYPE_OTHER;
}

/**
 * Sort key for a canonical cancer type. Unknown values sort last so
 * any escape-hatch row keeps the rest of the chart in NCDA order.
 */
export function cancerTypeOrderIndex(canonical: string): number {
  return CANCER_TYPE_ORDER.get(canonical) ?? CANCER_TYPE_OPTIONS.length;
}

export function isCanonicalCancerType(raw: unknown): raw is string {
  return typeof raw === "string" && CANCER_TYPE_SET.has(raw);
}
