/**
 * Plain-English copy for each Pipeline Guard family.
 *
 * Audience: knowledge authors and platform admins.
 * Default blocks target a reading age of about 11.
 */
export interface GuardTypeCopy {
  label: string;
  what: string;
}

export interface GuardFamilyCopy {
  key: string;
  title: string;
  what: string;
  why: string;
  ifWrong: string;
  accent: string;
  types: Record<string, GuardTypeCopy>;
}

export const GUARD_FAMILY_COPY: Record<string, GuardFamilyCopy> = {
  scope_guard: {
    key: "scope_guard",
    title: "Scope guard",
    what: "Stops LEO treating advice or plans as things that already happened.",
    why: "Notes often say \"call 999 if chest pain\" or \"consider starting a tablet\". That is advice, not a diagnosis.",
    ifWrong: "Reviewers can see fake findings, or real findings can be dropped.",
    accent: "#2E7D32",
    types: {
      safety_netting: {
        label: "Safety netting",
        what: "Patient advice such as \"come back if it gets worse\". Not a clinical event.",
      },
      recommendation: {
        label: "Recommendation",
        what: "A plan or suggestion, such as \"consider referral\". Not yet done.",
      },
    },
  },
  lab_value_guard: {
    key: "lab_value_guard",
    title: "Lab value guard",
    what: "Stops LEO turning a lab number into a disease.",
    why: "An eGFR result is a measurement. It is not kidney disease on its own.",
    ifWrong: "A blood test can look like a diagnosis in the summary.",
    accent: "#1565C0",
    types: {
      lab_pattern: {
        label: "Lab test name",
        what: "Names of tests this guard treats as measurements, not diseases.",
      },
    },
  },
  referral_routing_guard: {
    key: "referral_routing_guard",
    title: "Referral routing guard",
    what: "Keeps named tests and cancer sites. Drops \"referral submitted\" form wording.",
    why: "Referral forms repeat pathway labels. Those labels are not clinical facts.",
    ifWrong: "The summary can fill with form wording, or a real test can be dropped.",
    accent: "#E65100",
    types: {
      named_test: {
        label: "Named test",
        what: "Investigations that must be kept, such as FIT, CT, or colonoscopy.",
      },
      site: {
        label: "Cancer site",
        what: "Body sites used in suspected-cancer wording, such as breast or bowel.",
      },
      keep_action: {
        label: "Keep action",
        what: "Clinical actions that mention referral but are still real care.",
      },
    },
  },
  assertion_guard: {
    key: "assertion_guard",
    title: "Assertion guard",
    what: "Keeps status phrases such as \"ex-smoker\" marked as present.",
    why: "The words already say the status. A nearby \"not\" should not flip them to absent.",
    ifWrong: "Smoking status can vanish from the summary.",
    accent: "#6A1B9A",
    types: {
      lifestyle_concept: {
        label: "Lifestyle status",
        what: "Clinical codes whose preferred term already includes the status.",
      },
    },
  },
  entity_type_norm: {
    key: "entity_type_norm",
    title: "Entity-type normalisation",
    what: "Relabels words such as \"new episode\" and \"severe\" so they are not coded as diseases.",
    why: "Those words describe time or how bad something is. They are not conditions.",
    ifWrong: "Extra fake diagnoses can appear from qualifier words.",
    accent: "#00695C",
    types: {
      episode_marker: {
        label: "Episode marker",
        what: "Phrases that mark a new or ongoing episode, not a disease name.",
      },
      severity_modifier: {
        label: "Severity word",
        what: "Words such as mild, severe, or worsening. They qualify a finding.",
      },
    },
  },
  checkbox_norm: {
    key: "checkbox_norm",
    title: "Checkbox normaliser",
    what: "Marks admin form questions so LEO does not extract them as findings.",
    why: "\"Has the patient...\" is a prompt on the form, not something the patient has.",
    ifWrong: "Form questions can look like clinical facts.",
    accent: "#F57F17",
    types: {
      admin_question: {
        label: "Admin question",
        what: "Form prompts and tick-box labels that should not be coded.",
      },
    },
  },
  situation_lookup: {
    key: "situation_lookup",
    title: "Situation lookup",
    what: "Rewrites phrases such as \"two week wait referral\" into a standard lookup term.",
    why: "Coding search needs the usual wording, not local shorthand.",
    ifWrong: "The right clinical code can be missed.",
    accent: "#4527A0",
    types: {
      situation_lookup: {
        label: "Situation phrase",
        what: "A phrase that should map to a standard situation term, or be left alone.",
      },
    },
  },
  term_concept_blocklist: {
    key: "term_concept_blocklist",
    title: "Term concept blocklist",
    what: "Blocks a wrong code when a word has more than one meaning.",
    why: "FIT is a stool test in primary care, not a seizure.",
    ifWrong: "A common word can get a harmful wrong code.",
    accent: "#AD1457",
    types: {
      term_concept_blocklist: {
        label: "Blocked meaning",
        what: "A surface form that must not auto-code to a listed clinical code.",
      },
    },
  },
};

export function familyKind(key: string): string {
  if (key === "situation_lookup") return "Rewrite";
  if (key === "term_concept_blocklist") return "Block";
  if (key === "entity_type_norm") return "Relabel";
  return "Filter";
}

export const PATTERN_SYNTAX_COPY = {
  title: "How to read a pattern",
  intro: "A pattern is a search rule. Capital letters do not matter.",
  items: [
    "Plain words must appear in the note.",
    "A bar | means or. develop|notice matches either word.",
    "Brackets ( ) group a choice or extra words.",
    "Dots on a short label mean the rule was cut. Open the row to see the full rule.",
  ],
};

export const GUARD_FAMILY_KEYS = Object.keys(GUARD_FAMILY_COPY);

export const GUARD_FAMILIES = [
  { value: "all", label: "All families" },
  ...GUARD_FAMILY_KEYS.map((key) => ({
    value: key,
    label: GUARD_FAMILY_COPY[key].title,
  })),
];

export const RULE_TYPE_OPTIONS_BY_FAMILY: Record<
  string,
  Array<{ value: string; label: string }>
> = Object.fromEntries(
  GUARD_FAMILY_KEYS.map((key) => [
    key,
    Object.entries(GUARD_FAMILY_COPY[key].types).map(([value, typeCopy]) => ({
      value,
      label: typeCopy.label,
    })),
  ]),
);
