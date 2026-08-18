/**
 * Plain-English copy for each Pipeline Guard family.
 *
 * Audience: knowledge authors and platform admins.
 * Default blocks target a reading age of about 11.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
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
      pmh_list: {
        label: "Past history list",
        what: "Phrases such as PMHx or known that introduce a past medical history list.",
      },
    },
  },
  ignore_phrase: {
    key: "ignore_phrase",
    title: "Ignore this phrase",
    what: "Stops LEO extracting a phrase that reviewers have said is not a clinical fact.",
    why: "Operations can mark a phrase to ignore. Those rules need a list so authors can review or turn them off.",
    ifWrong: "A real finding can vanish, or junk wording can keep coming back.",
    accent: "#455A64",
    types: {
      suppress: {
        label: "Ignore phrase",
        what: "Drop this wording from later extracts.",
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
  body_structure_guard: {
    key: "body_structure_guard",
    title: "Body-part guard",
    what: "Keeps named body sites. Always keeps six reproductive organs.",
    why: "A finding such as numbness needs its site. A bare \"arm\" with no finding is noise.",
    ifWrong: "Sites vanish, or leftover anatomy is coded as a fact on its own.",
    accent: "#00838F",
    types: {
      always_keep: {
        label: "Always keep",
        what: "Reproductive organs kept for the gender check, even with no finding.",
      },
      keep_as_site: {
        label: "Keep as site",
        what: "Body parts kept so they can link to a finding or procedure.",
      },
      drop_orphan: {
        label: "Drop orphan",
        what: "Drops a keep-as-site part that never linked to a finding.",
      },
    },
  },
  fact_link_guard: {
    key: "fact_link_guard",
    title: "Fact-link guard",
    what: "Lists which fact links the pipeline may apply.",
    why: "Only same-phrase site, lab, and caused-by links should be stored.",
    ifWrong: "The letter can gain invented sites, or a real drug-reaction link is dropped.",
    accent: "#5D4037",
    types: {
      allowed_relation: {
        label: "Allowed link",
        what: "A relation type the runtime linker may apply, such as finding_site.",
      },
    },
  },
};

export function familyKind(key: string): string {
  if (key === "situation_lookup") return "Rewrite";
  if (key === "term_concept_blocklist") return "Block";
  if (key === "entity_type_norm") return "Relabel";
  if (key === "fact_link_guard") return "Allow";
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
