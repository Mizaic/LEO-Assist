import type { IntroRoleCopy } from "@leo/design-system";

// KNOWLEDGE_TAB_COPY -- role-aware intro copy for every tab in the admin
// Knowledge hub. See DI-LEO-AI-137 and R-LEO-AI-094.
//
// Readability rule: every `default` block must grade at Flesch-Kincaid 9
// or below. The other four role blocks may go to grade 12 for power-user
// language where needed (for example qa_ra_lead copy can name FMEA or
// ISO 14971). The test at __tests__/knowledge-copy-readability.test.ts
// pins the rule on the default blocks.

export type KnowledgeTabKey =
  | "training-data"
  | "surface-forms"
  | "context-rules"
  | "ai-instructions"
  | "clinical-guidelines"
  | "pathways"
  | "domains"
  | "terminology"
  | "ai-summarisation"
  | "test-patients";

export const KNOWLEDGE_TAB_COPY: Record<KnowledgeTabKey, IntroRoleCopy> = {
  "training-data": {
    default: {
      title: "Training Data",
      lede: "Teach LEO to code notes the way your team does.",
      how: "Pick a note, mark the code that fits, and save it.",
      what: "LEO uses saved notes to learn from and score itself on.",
    },
    clinician: {
      title: "Gold notes",
      lede: "A small set of real notes coded by a clinician.",
      how: "Open a note, confirm the code or fix it, and save.",
      what: "Your fix helps LEO get coding right for the next patient.",
    },
    staff: {
      title: "Gold dataset queue",
      lede: "This is the queue of notes waiting for your sign-off.",
      how: "Open the top note. Check the code. Approve or change it.",
      what: "Approved notes move into the gold set used to grade LEO.",
    },
    qa_ra_lead: {
      title: "Gold dataset (evidence)",
      lede: "Labelled notes used as the ground truth for accuracy scoring.",
      how: "Review inter-rater agreement, sign off on drift, and export the set.",
      what: "Exports feed into the quarterly accuracy report and the risk file.",
    },
    platform_admin: {
      title: "Gold dataset storage",
      lede: "Where labelled notes live and how much space they use.",
      how: "Check counts per tenant and archive old sets if needed.",
      what: "Kept sets keep scoring stable across releases.",
    },
  },

  "surface-forms": {
    default: {
      title: "Surface Forms",
      lede: "Match the words clinicians write to the codes LEO uses.",
      how: "Add a phrase, link it to a code, and save.",
      what: "LEO will pick up the phrase in new notes and code it.",
    },
    clinician: {
      title: "Phrase shortcuts",
      lede: "Local phrases your team writes that mean the same thing.",
      how: "Add a phrase and link it to the code you want LEO to pick.",
      what: "LEO reads the phrase as that code from now on.",
    },
    staff: {
      title: "Surface forms queue",
      lede: "Clinician phrases waiting to be linked to a SNOMED code.",
      how: "Search for the code. Link it. Save the pair.",
      what: "The next note that uses the phrase gets coded right.",
    },
    qa_ra_lead: {
      title: "Lexicon change log",
      lede: "Every surface form mapping, author, and review status.",
      how: "Audit new mappings weekly and retire unused ones.",
      what: "Keeps the lexicon explainable in a regulator inspection.",
    },
    platform_admin: {
      title: "Surface form rules",
      lede: "Lexicon size, import jobs, and per-tenant overrides.",
      how: "Run the bulk import and review job results.",
      what: "Large tenants share a base lexicon with local overrides.",
    },
  },

  "context-rules": {
    default: {
      title: "Context Rules",
      lede: "Tell LEO when a word changes meaning from the words around it.",
      how: "Pick a trigger word and say what it means in context.",
      what: "LEO will apply the rule whenever it sees the trigger.",
    },
    clinician: {
      title: "When words mean the other thing",
      lede: "A rule like 'family history of' means the patient does not have it.",
      how: "Pick a trigger and say what it flips the meaning to.",
      what: "LEO will spot the trigger and not code the patient with it.",
    },
    staff: {
      title: "Context rule review",
      lede: "ConText rules that flip meaning (negated, history, family).",
      how: "Check the trigger. Approve it or send it back.",
      what: "Approved rules run in the pipeline tonight.",
    },
    qa_ra_lead: {
      title: "ConText gate (NegEx + family)",
      lede: "Trigger phrases that flip an observation to negated, historic, family, or suspected.",
      how: "Audit new triggers weekly, verify dual-path parity, log sign-off.",
      what: "Keeps assertion handling consistent across runtime and Ask LEO.",
    },
    platform_admin: {
      title: "Context engine rules",
      lede: "Trigger phrases and the tenants each rule set is scoped to.",
      how: "Review which tenants share rule sets and which override them.",
      what: "Keeps rule scope transparent per tenant.",
    },
  },

  "ai-instructions": {
    default: {
      title: "AI Instructions",
      lede: "The prompts LEO uses when it asks a model a question.",
      how: "Open a prompt, change the wording, and save it.",
      what: "LEO uses the new wording from the next run onwards.",
    },
    clinician: {
      title: "How LEO is asked",
      lede: "The words LEO sends to a model to get a coding answer.",
      how: "Open a prompt to see what LEO asks and how it should reply.",
      what: "A clearer prompt means fewer borderline reviews for you.",
    },
    staff: {
      title: "Prompt library",
      lede: "The prompts you queue for review before a release.",
      how: "Diff the old and new prompt. Approve or send back.",
      what: "Approved prompts ship with the next deploy.",
    },
    qa_ra_lead: {
      title: "Prompt registry",
      lede: "Versioned prompts with change log, owner, and sign-off.",
      how: "Confirm the diff, record the risk impact, then sign.",
      what: "Sign-off locks the version used in production.",
    },
    platform_admin: {
      title: "Prompt template nodes",
      lede: "Prompts live as Neo4j nodes with version history.",
      how: "Pick a tenant to see which prompts are active for them.",
      what: "Per-tenant pinning lets you roll out prompts safely.",
    },
  },

  "clinical-guidelines": {
    default: {
      title: "Clinical Guidelines",
      lede: "Rules based on NICE and local guidance that LEO follows.",
      how: "Open a guideline, check the rule, and approve it.",
      what: "LEO checks each note against the rules and flags gaps.",
    },
    clinician: {
      title: "Guideline prompts",
      lede: "Simple rules like 'if BP is high, check it again'.",
      how: "Open the rule. Tick 'approve' if it matches your practice.",
      what: "LEO will show the prompt on the next matching patient.",
    },
    staff: {
      title: "Guidance rules queue",
      lede: "Rules drafted from NICE and local guides, waiting for sign-off.",
      how: "Read the rule. Check the code link. Approve or amend.",
      what: "Approved rules flag gaps in the next audit sweep.",
    },
    qa_ra_lead: {
      title: "Clinical guideline gate",
      lede: "Rule authoring, NICE mapping, and sign-off for safety-netting prompts.",
      how: "Verify citation. Confirm severity. Record approval.",
      what: "Sign-off is logged for ISO 13485 design-change evidence.",
    },
    platform_admin: {
      title: "Guideline scope per tenant",
      lede: "Which tenants have which rule sets switched on.",
      how: "Pick a tenant. Toggle a rule set. Review impact.",
      what: "Large tenants often pin rule sets to their local pathway.",
    },
  },

  pathways: {
    default: {
      title: "Pathways",
      lede: "The steps a patient goes through for a condition.",
      how: "Open a pathway, edit a step, and save it.",
      what: "LEO checks each patient's notes against the steps.",
    },
    clinician: {
      title: "Patient pathways",
      lede: "The care steps you expect for a patient with a condition.",
      how: "Open a pathway to see the steps and the target days.",
      what: "LEO tells you if a patient is behind on a step.",
    },
    staff: {
      title: "Pathway setup",
      lede: "The pathway rules LEO uses for audit and alerts.",
      how: "Pick a pathway. Edit or add a step. Save.",
      what: "Active patients on that pathway are re-scored overnight.",
    },
    qa_ra_lead: {
      title: "PlanDefinition authoring",
      lede: "FHIR PlanDefinitions that drive pathway segmentation and KPIs.",
      how: "Review steps, the milestone types they emit, and the version diff.",
      what: "Publishing a new version re-segments historic episodes.",
    },
    platform_admin: {
      title: "Pathway catalogue",
      lede: "Every pathway a tenant has switched on and its version.",
      how: "Pick a tenant. Check which pathways are live.",
      what: "Tenants can pin a pathway to a version for stability.",
    },
  },

  domains: {
    default: {
      title: "Domains",
      lede: "Groups of SNOMED codes LEO treats as the same thing.",
      how: "Open a domain, add or remove a code, and save.",
      what: "Notes that match any code in the domain count as that domain.",
    },
    clinician: {
      title: "Code groups",
      lede: "A set of codes LEO treats as one concept (for example 'diabetes').",
      how: "Open a domain. Add a missing code. Save.",
      what: "The next audit uses the updated group for counts.",
    },
    staff: {
      title: "Domain lists",
      lede: "SNOMED code lists grouped by meaning for QOF and audit.",
      how: "Search a code. Add it to the domain. Save.",
      what: "Domain changes re-score the next audit run.",
    },
    qa_ra_lead: {
      title: "Domain set versioning",
      lede: "Versioned SNOMED ECL expressions and enumerated code lists.",
      how: "Check ECL syntax. Diff. Approve or send back.",
      what: "Approved sets are locked and carry a change log.",
    },
    platform_admin: {
      title: "Domain publish state",
      lede: "Which domain versions are live per tenant.",
      how: "Pick a tenant. Confirm the active version.",
      what: "Pinning stops a shared domain update from shifting their numbers.",
    },
  },

  "ai-summarisation": {
    default: {
      title: "AI Summarisation",
      lede: "Try out the SBAR summary that LEO writes for a patient.",
      how: "Pick a patient, add a referral or a note, then run.",
      what: "You see each section as it is written. Test only.",
    },
    clinician: {
      title: "Try the SBAR helper",
      lede: "Run a draft SBAR for a patient to see what LEO would write.",
      how: "Choose the referral or note and click run.",
      what: "Use it to give us feedback. Do not use it for care yet.",
    },
    staff: {
      title: "SBAR generation playground",
      lede: "Build a payload and see the live four-stage run.",
      how: "Add the situation, background and any guideline ids.",
      what: "Outputs help you tune prompts before they ship.",
    },
    qa_ra_lead: {
      title: "SBAR generation harness",
      lede: "Manual entry point to the production sbar_requested queue.",
      how: "Compose a payload, watch SSE stages, inspect the persisted Assessment.",
      what: "Use to verify prompt + roaring-bitmap behaviour against fixtures.",
    },
    platform_admin: {
      title: "SBAR pipeline test surface",
      lede: "Direct enqueue to the pipeline-jobs queue with the SBAR contract.",
      how: "Submit a payload and watch the worker pick it up.",
      what: "Useful for smoke-testing worker scale-out and Redis relay.",
    },
  },

  "test-patients": {
    default: {
      title: "Test Patients",
      lede: "Fake patients you can use to check the AI before a change goes live.",
      how: "Pick what you want to test, then build or copy a patient.",
      what: "You can replay them any time to see if the AI still works.",
    },
    clinician: {
      title: "Test patients",
      lede: "Pretend patients used to check the tool, never real people.",
      how: "Open one to see what notes and codes it carries.",
      what: "Test patients are tagged with test_ so they cannot be mistaken for real ones.",
    },
    staff: {
      title: "Test patient library",
      lede: "One place to keep test patients for every part of the AI.",
      how: "Pick which part of the AI to test, then build a patient or copy a real one.",
      what: "Replay any time to spot a change in how the AI behaves.",
    },
    qa_ra_lead: {
      title: "Test patient library (regression bench)",
      lede: "Centralised fixtures for NLP, episode build, guideline firing and SBAR generation.",
      how: "Filter by aspect, replay before sign-off, and review per-aspect drift in one place.",
      what: "Each fixture carries an is_test flag and a separate :TestPatient label so leakage into clinician surfaces is structurally impossible (R-8C0CC94B).",
    },
    platform_admin: {
      title: "Test patient graph",
      lede: "Synthetic :TestPatient subgraph next to real :Patient rows.",
      how: "Use the clone-from-real action to seed a fixture from a real patient with PII stripped.",
      what: "All cloned encounters and documents carry is_test = true so any property-level filter can also exclude them.",
    },
  },

  terminology: {
    default: {
      title: "Terminology",
      lede: "The SNOMED codes LEO knows about and how they link.",
      how: "Search a code, open it, and check its links.",
      what: "Links drive how LEO groups codes in audits.",
    },
    clinician: {
      title: "Code browser",
      lede: "Look up a SNOMED code and see what sits above or below it.",
      how: "Type a word or code. Open the result.",
      what: "You can copy the code into a consult note.",
    },
    staff: {
      title: "Terminology tools",
      lede: "SNOMED browser, mapping, and release notes.",
      how: "Use the browser to find a code. Check the map to local terms.",
      what: "Mappings feed into the surface form list.",
    },
    qa_ra_lead: {
      title: "Ontology management",
      lede: "Active SNOMED edition, version, and pending ingest jobs.",
      how: "Verify the edition. Run a release upgrade in staging first.",
      what: "New editions carry breaking changes that need impact review.",
    },
    platform_admin: {
      title: "Terminology subsystem",
      lede: "Which SNOMED edition is live and when the next refresh runs.",
      how: "Trigger a refresh or pin an edition per tenant.",
      what: "Refreshes pull new terms and retire superseded codes.",
    },
  },
};
