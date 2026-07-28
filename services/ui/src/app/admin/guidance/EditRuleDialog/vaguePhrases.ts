/**
 * Vague-phrase detector and concept suggestion lookup.
 *
 * Many NICE recommendations contain phrases like "symptoms of lung
 * cancer" or "CXR indicative of malignancy". These read clearly to a
 * clinician but cannot be coded against a patient record because the
 * system does not know which specific symptoms or findings to look for.
 *
 * This module:
 *   1. Detects whether a chip's preferred_term is a vague phrase.
 *   2. Maps the captured topic ("lung cancer", "sepsis", ...) to a
 *      curated list of specific SNOMED CT concepts the reviewer can
 *      add as siblings in the rule.
 *
 * The deterministic suggestion table covers the most common topics
 * seen in NICE NG12. Unknown topics still open the coach so the
 * reviewer can use "Ask LEO for ideas" (LLM term expansion + bulk
 * SNOMED resolve) instead of dead-ending.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import { friendlyTerm } from "./copy";

export interface VaguePhraseMatch {
  isVague: boolean;
  /** Normalised topic captured from the regex (lowercased). */
  topic: string | null;
  /** Identifier for the matched pattern, useful for telemetry. */
  patternLabel: string | null;
  /** Plain-English explanation shown in the Coach popover. */
  reason: string | null;
}

export interface ConceptSuggestion {
  snomed_concept_id: string;
  preferred_term: string;
  /** Optional one-line note shown next to the suggestion. */
  rationale?: string;
}

interface PatternDef {
  label: string;
  regex: RegExp;
  reason: string;
  topicGroup: number;
}

const PATTERNS: PatternDef[] = [
  {
    label: "symptoms_of",
    regex: /^\s*(?:signs?\s*(?:and|&|\+)?\s*)?symptoms?\s+of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which symptoms LEO should look for. Pick the specific symptoms below or search for more.",
  },
  {
    label: "signs_of",
    regex: /^\s*signs?\s+of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which signs LEO should look for. Pick the specific signs below or search for more.",
  },
  {
    label: "trailing_symptoms",
    regex: /^\s*(.+?)\s+symptoms?\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which symptoms LEO should look for. Pick the specific symptoms below or search for more.",
  },
  {
    label: "indicative_of",
    regex: /\bindicative\s+of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings count as indicative. Pick specific findings below or search for more.",
  },
  {
    label: "suggestive_of",
    regex: /\bsuggestive\s+of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings count as suggestive. Pick specific findings below or search for more.",
  },
  {
    // NG12 1.7.2 "dermoscopy suggests melanoma"; 1.1.4 "findings that
    // suggest mesothelioma". Distinct from "suggestive of" above and
    // from "may/might/could suggest" (may_indicate).
    label: "suggests",
    regex: /\bsuggests?\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings count. Pick specific findings below or ask LEO for ideas.",
  },
  {
    label: "consistent_with",
    regex: /\bconsistent\s+with\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings count as consistent. Pick specific findings below or search for more.",
  },
  {
    label: "features_of",
    regex: /\bfeatures?\s+of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which features count. Pick specific features below or search for more.",
  },
  {
    // NG12 1.7.4 / 1.7.5 / 1.7.6: "skin lesion that raises the suspicion
    // of a basal cell carcinoma" -- Ask LEO for concrete lesion features.
    label: "raises_suspicion_of",
    regex:
      /\braises?\s+(?:the\s+)?suspicion\s+of\s+(?:a\s+|an\s+)?(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings raise the suspicion. Pick specific findings below or ask LEO for ideas.",
  },
  {
    label: "suspected",
    regex: /^\s*suspected\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say what would make the suspicion concrete. Pick specific findings below or search for more.",
  },
  {
    // NG12 1.7.6 delay gate: "particular concern that a delay may..."
    label: "concern_that",
    regex: /\b(?:particular\s+)?concern\s+that\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase is a clinical judgement, not a single code. Ask LEO for ideas or search for the findings that make delay unsafe.",
  },
  {
    label: "possible",
    regex: /^\s*possible\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say what would make the diagnosis possible. Pick specific findings below or search for more.",
  },
  {
    label: "concern_of",
    regex: /^\s*(?:clinical\s+)?concern\s+(?:about|of|for)\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say what would raise the concern. Pick specific findings below or search for more.",
  },
  {
    label: "risk_of",
    regex: /^\s*risk\s+(?:of|for)\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings raise the risk. Pick specific findings below or search for more.",
  },
  {
    label: "abnormal",
    regex: /^\s*abnormal\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which abnormality. Pick specific findings below or search for more.",
  },
  {
    label: "red_flags",
    regex: /^\s*red\s+flags?\s+(?:for|of)\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not list the red flags. Pick the specific red-flag symptoms below or search for more.",
  },
  {
    label: "cxr_findings",
    regex: /^\s*(?:CXR|chest\s+x[- ]?ray)\s+(?:findings?|features?|changes?|abnormalit(?:y|ies))?\s*(?:of\s+)?(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which X-ray findings count. Pick specific findings below or search for more.",
  },
  {
    label: "may_indicate",
    regex: /\b(?:may|might|could)\s+(?:be\s+)?(?:indicate|indicating|suggest|suggesting)\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which findings would count. Pick specific findings below or ask LEO for ideas.",
  },
  {
    label: "changes_of",
    regex:
      /^\s*(?:skin|breast|chest|bowel|voice)\s+changes?\s+(?:suggestive\s+|indicative\s+)?of\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not say which changes count. Pick specific findings below or ask LEO for ideas.",
  },
  {
    // Catch-all for novel multi-word "X of Y" clinical topics that missed
    // the stricter patterns above -- opens the coach so Ask LEO can help
    // when the curated suggestion table has nothing for that topic.
    label: "topic_of",
    regex:
      /^\s*(?:findings?|features?|markers?|evidence|presentation)\s+(?:of|for)\s+(.+?)\s*$/i,
    topicGroup: 1,
    reason:
      "This phrase does not list the specific findings. Ask LEO for ideas or search for each one.",
  },
];

/**
 * Inspect a chip's preferred_term and decide whether it is too vague
 * to evaluate against a patient record.
 */
export function detectVaguePhrase(text: string | null | undefined): VaguePhraseMatch {
  const empty: VaguePhraseMatch = {
    isVague: false,
    topic: null,
    patternLabel: null,
    reason: null,
  };
  if (!text) return empty;
  const stripped = friendlyTerm(text);
  if (!stripped) return empty;
  for (const p of PATTERNS) {
    const m = p.regex.exec(stripped);
    if (m) {
      const topic = (m[p.topicGroup] ?? "").trim().toLowerCase();
      if (!topic) continue;
      return {
        isVague: true,
        topic,
        patternLabel: p.label,
        reason: p.reason,
      };
    }
  }
  return empty;
}

// ---- Topic normalisation + suggestion lookup -----------------------------

/**
 * Normalise free-text topics from the captured regex to a canonical
 * key in SUGGESTIONS. Includes common aliases.
 */
const TOPIC_NORMALISATION: Record<string, string> = {
  "lung cancer": "lung_cancer",
  lung: "lung_cancer",
  pulmonary: "lung_cancer",
  "breast cancer": "breast_cancer",
  breast: "breast_cancer",
  "colorectal cancer": "colorectal_cancer",
  "bowel cancer": "colorectal_cancer",
  bowel: "colorectal_cancer",
  colorectal: "colorectal_cancer",
  "prostate cancer": "prostate_cancer",
  prostate: "prostate_cancer",
  "ovarian cancer": "ovarian_cancer",
  ovarian: "ovarian_cancer",
  "pancreatic cancer": "pancreatic_cancer",
  pancreas: "pancreatic_cancer",
  "liver cancer": "liver_cancer",
  liver: "liver_cancer",
  "bladder cancer": "bladder_cancer",
  bladder: "bladder_cancer",
  cancer: "cancer_generic",
  malignancy: "cancer_generic",
  sepsis: "sepsis",
  meningitis: "meningitis",
  stroke: "stroke",
  tia: "stroke",
  "transient ischaemic attack": "stroke",
  mi: "myocardial_infarction",
  "myocardial infarction": "myocardial_infarction",
  "heart attack": "myocardial_infarction",
  dehydration: "dehydration",
};

/**
 * Curated suggestions per canonical topic. SNOMED CT IDs are the
 * widely-used international concept identifiers; using real IDs means
 * the reviewer can click to add a suggestion without going through
 * the search panel.
 */
const SUGGESTIONS: Record<string, ConceptSuggestion[]> = {
  lung_cancer: [
    { snomed_concept_id: "49727002", preferred_term: "Cough", rationale: "Persistent cough lasting 3+ weeks" },
    { snomed_concept_id: "66857006", preferred_term: "Haemoptysis", rationale: "Coughing up blood" },
    { snomed_concept_id: "29857009", preferred_term: "Chest pain" },
    { snomed_concept_id: "267036007", preferred_term: "Dyspnoea", rationale: "Shortness of breath" },
    { snomed_concept_id: "89362005", preferred_term: "Weight loss", rationale: "Unexplained weight loss" },
    { snomed_concept_id: "84229001", preferred_term: "Fatigue" },
    { snomed_concept_id: "79890006", preferred_term: "Loss of appetite" },
  ],
  breast_cancer: [
    { snomed_concept_id: "247429001", preferred_term: "Breast lump", rationale: "Unexplained breast lump" },
    { snomed_concept_id: "302833002", preferred_term: "Nipple discharge", rationale: "Bloody or unilateral" },
    { snomed_concept_id: "248382006", preferred_term: "Nipple retraction" },
    { snomed_concept_id: "247426009", preferred_term: "Skin change of breast", rationale: "Dimpling, peau d'orange" },
    { snomed_concept_id: "300963000", preferred_term: "Lump in axilla", rationale: "Unexplained axillary lump" },
  ],
  colorectal_cancer: [
    { snomed_concept_id: "12063002", preferred_term: "Rectal bleeding", rationale: "Unexplained rectal bleeding" },
    { snomed_concept_id: "62315008", preferred_term: "Diarrhoea", rationale: "Persistent change in bowel habit" },
    { snomed_concept_id: "271737000", preferred_term: "Anaemia", rationale: "Unexplained iron deficiency anaemia" },
    { snomed_concept_id: "21522001", preferred_term: "Abdominal pain" },
    { snomed_concept_id: "89362005", preferred_term: "Weight loss" },
    { snomed_concept_id: "300473004", preferred_term: "Abdominal mass" },
  ],
  prostate_cancer: [
    { snomed_concept_id: "60241006", preferred_term: "Lower urinary tract symptoms" },
    { snomed_concept_id: "34436003", preferred_term: "Nocturia", rationale: "Waking to pass urine" },
    { snomed_concept_id: "75088002", preferred_term: "Erectile dysfunction" },
    { snomed_concept_id: "34436003", preferred_term: "Visible haematuria" },
  ],
  ovarian_cancer: [
    { snomed_concept_id: "60728008", preferred_term: "Ascites", rationale: "Abdominal swelling" },
    { snomed_concept_id: "300473004", preferred_term: "Pelvic mass" },
    { snomed_concept_id: "21522001", preferred_term: "Abdominal pain", rationale: "Persistent" },
    { snomed_concept_id: "162031009", preferred_term: "Bloating", rationale: "Persistent abdominal bloating" },
    { snomed_concept_id: "79890006", preferred_term: "Early satiety / loss of appetite" },
  ],
  pancreatic_cancer: [
    { snomed_concept_id: "18165001", preferred_term: "Jaundice", rationale: "Painless jaundice in 60+" },
    { snomed_concept_id: "21522001", preferred_term: "Upper abdominal pain" },
    { snomed_concept_id: "20062006", preferred_term: "Back pain" },
    { snomed_concept_id: "89362005", preferred_term: "Weight loss" },
    { snomed_concept_id: "73211009", preferred_term: "New-onset diabetes" },
  ],
  liver_cancer: [
    { snomed_concept_id: "18165001", preferred_term: "Jaundice" },
    { snomed_concept_id: "21522001", preferred_term: "Upper abdominal pain" },
    { snomed_concept_id: "300473004", preferred_term: "Abdominal mass", rationale: "Hepatomegaly" },
    { snomed_concept_id: "89362005", preferred_term: "Weight loss" },
    { snomed_concept_id: "60728008", preferred_term: "Ascites" },
  ],
  bladder_cancer: [
    { snomed_concept_id: "53298000", preferred_term: "Visible haematuria" },
    { snomed_concept_id: "60241006", preferred_term: "Lower urinary tract symptoms" },
    { snomed_concept_id: "49650001", preferred_term: "Recurrent urinary tract infection" },
  ],
  cancer_generic: [
    { snomed_concept_id: "89362005", preferred_term: "Weight loss", rationale: "Unexplained" },
    { snomed_concept_id: "84229001", preferred_term: "Fatigue", rationale: "Unexplained, persistent" },
    { snomed_concept_id: "42984000", preferred_term: "Night sweats" },
    { snomed_concept_id: "271737000", preferred_term: "Anaemia", rationale: "Unexplained" },
    { snomed_concept_id: "248536006", preferred_term: "Lymphadenopathy", rationale: "Unexplained lymph node enlargement" },
  ],
  sepsis: [
    { snomed_concept_id: "386661006", preferred_term: "Fever" },
    { snomed_concept_id: "271823003", preferred_term: "Tachycardia", rationale: "Heart rate over 90" },
    { snomed_concept_id: "271825005", preferred_term: "Tachypnoea", rationale: "Respiratory rate over 20" },
    { snomed_concept_id: "45007003", preferred_term: "Hypotension", rationale: "Systolic BP under 90" },
    { snomed_concept_id: "419045004", preferred_term: "Altered mental status" },
    { snomed_concept_id: "703528001", preferred_term: "Mottled skin" },
  ],
  meningitis: [
    { snomed_concept_id: "21522001", preferred_term: "Headache", rationale: "Severe headache" },
    { snomed_concept_id: "161891005", preferred_term: "Neck stiffness" },
    { snomed_concept_id: "386661006", preferred_term: "Fever" },
    { snomed_concept_id: "409668002", preferred_term: "Photophobia" },
    { snomed_concept_id: "23924001", preferred_term: "Non-blanching rash" },
  ],
  stroke: [
    { snomed_concept_id: "44695005", preferred_term: "Facial weakness" },
    { snomed_concept_id: "26544005", preferred_term: "Arm weakness" },
    { snomed_concept_id: "8011004", preferred_term: "Speech disturbance" },
    { snomed_concept_id: "246636008", preferred_term: "Sudden onset" },
    { snomed_concept_id: "246105005", preferred_term: "Loss of vision in one eye" },
  ],
  myocardial_infarction: [
    { snomed_concept_id: "29857009", preferred_term: "Chest pain", rationale: "Central, crushing" },
    { snomed_concept_id: "267036007", preferred_term: "Dyspnoea" },
    { snomed_concept_id: "422587007", preferred_term: "Nausea" },
    { snomed_concept_id: "415690000", preferred_term: "Sweating", rationale: "Diaphoresis" },
    { snomed_concept_id: "274640006", preferred_term: "Pain radiating to arm or jaw" },
  ],
  dehydration: [
    { snomed_concept_id: "271737000", preferred_term: "Decreased urine output" },
    { snomed_concept_id: "247409001", preferred_term: "Dry mouth" },
    { snomed_concept_id: "271823003", preferred_term: "Tachycardia" },
    { snomed_concept_id: "45007003", preferred_term: "Hypotension" },
    { snomed_concept_id: "419045004", preferred_term: "Altered mental status" },
  ],
};

/**
 * Look up suggested specific concepts for a captured topic. Returns
 * an empty array if the topic is unknown; the Coach popover then
 * shows a "Search for specific concepts" call-to-action.
 */
export function suggestConceptsForTopic(topic: string | null): ConceptSuggestion[] {
  if (!topic) return [];
  const key = normaliseTopic(topic);
  return SUGGESTIONS[key] ?? [];
}

export function normaliseTopic(topic: string): string {
  const lower = topic.toLowerCase().trim();
  if (TOPIC_NORMALISATION[lower]) return TOPIC_NORMALISATION[lower];
  // Try stripping common qualifiers
  const stripped = lower
    .replace(/^primary\s+/, "")
    .replace(/^secondary\s+/, "")
    .replace(/^suspected\s+/, "")
    .replace(/^possible\s+/, "");
  return TOPIC_NORMALISATION[stripped] ?? lower;
}
