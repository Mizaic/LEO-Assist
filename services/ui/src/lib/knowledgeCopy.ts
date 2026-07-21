/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
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
  | "results-labs"
  | "validation-lab";

export const KNOWLEDGE_TAB_COPY: Record<KnowledgeTabKey, IntroRoleCopy> = {
  "training-data": {
    default: {
      title: "Training Data",
      lede: "Teach LEO to code notes the way your team does.",
      how: "Pick a note, mark the code that fits, and save it.",
      what: "LEO uses saved notes to learn from and score itself on.",
    },
    triage_clinician: {
      title: "Gold notes",
      lede: "A small set of real notes coded by a clinician.",
      how: "Open a note, confirm the code or fix it, and save.",
      what: "Your fix helps LEO get coding right for the next patient.",
    },
    clinical_administrator: {
      title: "Gold dataset queue",
      lede: "This is the queue of notes waiting for your sign-off.",
      how: "Open the top note. Check the code. Approve or change it.",
      what: "Approved notes move into the gold set used to grade LEO.",
    },
    auditor: {
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
    triage_clinician: {
      title: "Phrase shortcuts",
      lede: "Local phrases your team writes that mean the same thing.",
      how: "Add a phrase and link it to the code you want LEO to pick.",
      what: "LEO reads the phrase as that code from now on.",
    },
    clinical_administrator: {
      title: "Surface forms queue",
      lede: "Clinician phrases waiting to be linked to a SNOMED code.",
      how: "Search for the code. Link it. Save the pair.",
      what: "The next note that uses the phrase gets coded right.",
    },
    auditor: {
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
    triage_clinician: {
      title: "When words mean the other thing",
      lede: "A rule like 'family history of' means the patient does not have it.",
      how: "Pick a trigger and say what it flips the meaning to.",
      what: "LEO will spot the trigger and not code the patient with it.",
    },
    clinical_administrator: {
      title: "Context rule review",
      lede: "ConText rules that flip meaning (negated, history, family).",
      how: "Check the trigger. Approve it or send it back.",
      what: "Approved rules run in the pipeline tonight.",
    },
    auditor: {
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
    triage_clinician: {
      title: "How LEO is asked",
      lede: "The words LEO sends to a model to get a coding answer.",
      how: "Open a prompt to see what LEO asks and how it should reply.",
      what: "A clearer prompt means fewer borderline reviews for you.",
    },
    clinical_administrator: {
      title: "Prompt library",
      lede: "The prompts you queue for review before a release.",
      how: "Diff the old and new prompt. Approve or send back.",
      what: "Approved prompts ship with the next deploy.",
    },
    auditor: {
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
    triage_clinician: {
      title: "Guideline prompts",
      lede: "Simple rules like 'if BP is high, check it again'.",
      how: "Open the rule. Tick 'approve' if it matches your practice.",
      what: "LEO will show the prompt on the next matching patient.",
    },
    clinical_administrator: {
      title: "Guidance rules queue",
      lede: "Rules drafted from NICE and local guides, waiting for sign-off.",
      how: "Read the rule. Check the code link. Approve or amend.",
      what: "Approved rules flag gaps in the next audit sweep.",
    },
    auditor: {
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
      lede: "Durable workflows made from reusable clinical processing steps.",
      how: "Open a pathway, check each step's event, graph inputs, and saved outputs.",
      what: "LEO runs each step independently and records what it produced.",
    },
    triage_clinician: {
      title: "Patient pathways",
      lede: "The care steps you expect for a patient with a condition.",
      how: "Open a pathway to see the steps and the target days.",
      what: "LEO tells you if a patient is behind on a step.",
    },
    clinical_administrator: {
      title: "Pathway setup",
      lede: "The durable pathway rules LEO uses for audit, alerts, and referral workflows.",
      how: "Pick a pathway. Check durable step wiring and publish a reviewed version.",
      what: "Each active step reloads data from Neo4j and saves its result.",
    },
    auditor: {
      title: "Durable workflow authoring",
      lede: "FHIR PlanDefinitions that drive pub/sub clinical workflow steps.",
      how: "Review triggers, persisted artefacts, event edges, and the version diff.",
      what: "Publishing a new version changes the governed processing contract.",
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
    triage_clinician: {
      title: "Code groups",
      lede: "A set of codes LEO treats as one concept (for example 'diabetes').",
      how: "Open a domain. Add a missing code. Save.",
      what: "The next audit uses the updated group for counts.",
    },
    clinical_administrator: {
      title: "Domain lists",
      lede: "SNOMED code lists grouped by meaning for QOF and audit.",
      how: "Search a code. Add it to the domain. Save.",
      what: "Domain changes re-score the next audit run.",
    },
    auditor: {
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

  "validation-lab": {
    default: {
      title: "Validation Lab",
      lede: "One place to build a test patient, run the referral, and save gold.",
      how: "Add a patient, PMH, and encounters, then write and submit a referral.",
      what: "One testing path for extraction, codes, rules, and SBAR.",
    },
    triage_clinician: {
      title: "Validation Lab",
      lede: "Check that LEO still matches the cases your team trusts.",
      how: "Open a case, run it, and review the SBAR in the shared widget.",
      what: "Gold cases stop silent drift when prompts or plans change.",
    },
    clinical_administrator: {
      title: "Validation Lab",
      lede: "One patient-building flow with a single gold contract per case.",
      how: "New patient, add PMH and encounters, write the referral, submit.",
      what: "Replaces separate test-patient and harness pages.",
    },
    auditor: {
      title: "Validation Lab (evidence)",
      lede: "Production-shaped patients run through the real referral pipeline.",
      how: "Persist like production by default. Dry-run cannot promote gold.",
      what: "Supports DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B.",
    },
    platform_admin: {
      title: "Validation Lab",
      lede: "Admin surface for :ValidationCase patients and their pipeline runs.",
      how: "Build a patient with the wizard, then run and promote gold.",
      what: "Pathway probes stay on the pathway builder for plan authoring only.",
    },
  },

  terminology: {
    default: {
      title: "Terminology",
      lede: "The SNOMED codes LEO knows about and how they link.",
      how: "Search a code, open it, and check its links.",
      what: "Links drive how LEO groups codes in audits.",
    },
    triage_clinician: {
      title: "Code browser",
      lede: "Look up a SNOMED code and see what sits above or below it.",
      how: "Type a word or code. Open the result.",
      what: "You can copy the code into a consult note.",
    },
    clinical_administrator: {
      title: "Terminology tools",
      lede: "SNOMED browser, mapping, and release notes.",
      how: "Use the browser to find a code. Check the map to local terms.",
      what: "Mappings feed into the surface form list.",
    },
    auditor: {
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

  "results-labs": {
    default: {
      title: "Results and Labs",
      lede: "Set the ranges LEO uses to read lab results.",
      how: "Pick a lab code, add its unit rules and safe ranges, then save.",
      what: "LEO uses this to spot high, low, and out-of-range results.",
    },
    triage_clinician: {
      title: "Lab result rules",
      lede: "The normal ranges and result meanings used by LEO.",
      how: "Check the lab, unit, and SNOMED finding match your practice.",
      what: "Correct ranges help LEO explain why a result is abnormal.",
    },
    clinical_administrator: {
      title: "Lab config queue",
      lede: "Lab ranges, unit conversions, and abnormal finding codes.",
      how: "Add the observable code, accepted units, ranges, and findings.",
      what: "Saved config is used by guideline tests and result alerts.",
    },
    auditor: {
      title: "Lab metadata control",
      lede: "Governed reference ranges and interpretation mappings for lab safety checks.",
      how: "Review source, demographic bands, unit conversion, and derived finding codes.",
      what: "This supports traceable abnormal-result classification evidence.",
    },
    platform_admin: {
      title: "Lab metadata store",
      lede: "Knowledge graph config for result ranges and unit conversions.",
      how: "Seed defaults, review manual edits, and check missing-range warnings.",
      what: "A single source stops runtime paths from drifting apart.",
    },
  },

};
