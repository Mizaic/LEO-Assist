/**
 * Clinical abbreviation expansion for SNOMED terminology search.
 *
 * Source: auditor_2 blood_test_jsons (test/component names) plus
 * well-known UK primary care blood test abbreviations.
 *
 * Used to expand query tokens before sending to the full-text search
 * index so that e.g. "TSH" matches "Serum thyroid stimulating hormone
 * level (observable entity)" without requiring the user to type the
 * full term. The displayed search box is never changed.
 *
 * Keys are matched case-insensitively as whole tokens (split on
 * whitespace/punctuation). Longer keys are tested first so "HbA1c"
 * wins over the shorter "Hb" prefix.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
const RAW: Record<string, string> = {
  // -- From auditor_2 blood_test_jsons (test-name abbreviations) ----------
  "5-hiaa":      "5-hydroxyindoleacetic acid",
  "achr":        "acetylcholine receptor",
  "afb":         "acid fast bacillus",
  "alt":         "alanine aminotransferase",
  "alp":         "alkaline phosphatase",
  "ana":         "antinuclear antibody",
  "apoe":        "apolipoprotein E",
  "ast":         "aspartate aminotransferase",
  "bnp":         "B-type natriuretic peptide",
  "ca125":       "cancer antigen 125",
  "ca19-9":      "cancer antigen 19-9",
  "cea":         "carcinoembryonic antigen",
  "ck":          "creatine kinase",
  "cmv":         "cytomegalovirus",
  "crp":         "C-reactive protein",
  "epo":         "erythropoietin",
  "esr":         "erythrocyte sedimentation rate",
  "fbc":         "full blood count",
  "ggt":         "gamma-glutamyl transferase",
  "hcg":         "human chorionic gonadotrophin",
  "ldh":         "lactate dehydrogenase",
  "psa":         "prostate specific antigen",
  "pt":          "prothrombin time",
  "inr":         "international normalised ratio",
  "pt/inr":      "prothrombin time international normalised ratio",
  "shbg":        "sex hormone binding globulin",
  "tsh":         "thyroid stimulating hormone",
  "vma":         "vanillylmandelic acid",
  "vldl":        "very low density lipoprotein",

  // -- From auditor_2 component names -------------------------------------
  "hct":         "haematocrit packed cell volume",
  "mch":         "mean corpuscular haemoglobin",
  "mchc":        "mean corpuscular haemoglobin concentration",
  "mcv":         "mean corpuscular volume",
  "mpv":         "mean platelet volume",
  "rbc":         "red blood cell",
  "rdw":         "red cell distribution width",
  "wbc":         "white blood cell",

  // -- Additional well-known UK primary care abbreviations ----------------
  "hba1c":       "glycated haemoglobin",
  "hb":          "haemoglobin",
  "egfr":        "estimated glomerular filtration rate",
  "lft":         "liver function test",
  "lfts":        "liver function tests",
  "tft":         "thyroid function test",
  "tfts":        "thyroid function tests",
  "ft3":         "free triiodothyronine",
  "ft4":         "free thyroxine",
  "t3":          "triiodothyronine",
  "t4":          "thyroxine",
  "pth":         "parathyroid hormone",
  "fsh":         "follicle stimulating hormone",
  "lh":          "luteinising hormone",
  "acth":        "adrenocorticotropic hormone",
  "adh":         "antidiuretic hormone vasopressin",
  "afp":         "alpha fetoprotein",
  "anca":        "antineutrophil cytoplasmic antibody",
  "b12":         "vitamin B12 cobalamin",
  "hdl":         "high density lipoprotein",
  "ldl":         "low density lipoprotein",
  "nt-probnp":   "N-terminal pro-B-type natriuretic peptide",
  "aptt":        "activated partial thromboplastin time",
  "ptt":         "partial thromboplastin time",
  "plt":         "platelet",
  "tpmt":        "thiopurine methyltransferase",
  "u&e":         "urea electrolytes",
  "ue":          "urea electrolytes",
  "wcc":         "white cell count",
  "tibc":        "total iron binding capacity",
  "uibc":        "unsaturated iron binding capacity",
  "ferr":        "ferritin",
  "fol":         "folate",
  "folate":      "folate folic acid",
  "trig":        "triglycerides",
  "chol":        "cholesterol",
  "amyl":        "amylase",
  "lip":         "lipase",
  "alb":         "albumin",
  "bili":        "bilirubin",
  "creat":       "creatinine",
  "urea":        "urea blood urea nitrogen",
  "gluc":        "glucose",
  "hba":         "haemoglobin A",
};

/**
 * Longest-first sorted entries so "hba1c" is tested before "hb",
 * "nt-probnp" before "bnp", etc.
 */
const ENTRIES = Object.entries(RAW).sort(([a], [b]) => b.length - a.length);

/** Separator pattern used to split/reconstruct query tokens. */
const SEP = /(\s+)/;

/**
 * Expand abbreviations in a query string.
 * Tokens are matched case-insensitively as whole words.
 * The original token is kept alongside the expansion so the full-text
 * index can match on either form:
 *   "TSH" -> "TSH thyroid stimulating hormone"
 */
export function expandAbbreviations(q: string): string {
  return q
    .split(SEP)
    .map((token) => {
      if (/^\s+$/.test(token)) return token;
      const lower = token.toLowerCase().replace(/[.,;:()]+$/, "");
      const match = ENTRIES.find(([k]) => k === lower);
      if (!match) return token;
      return `${token} ${match[1]}`;
    })
    .join("");
}
