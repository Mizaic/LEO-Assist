/**
 * Plain-English copy for each Context Rule category.
 *
 * Audience: knowledge authors, clinicians, and auditors.
 */
import type { ContextRule, ContextWorkedExample } from "./types";

export interface CategoryCopy {
  key: string;
  title: string;
  what: string;
  why: string;
  ifWrong: string;
  accent: string;
  withoutGuard: string;
  withGuard: string;
  dataChange: string;
}

export const CATEGORY_COPY: Record<string, CategoryCopy> = {
  NEGATED_EXISTENCE: {
    key: "NEGATED_EXISTENCE",
    title: "Not present",
    what: "Marks a nearby finding as not present.",
    why: "Notes say \"nil chest pain\" or \"no evidence of infection\". That is a check that found nothing.",
    ifWrong: "The patient can be coded with a problem they do not have.",
    accent: "#B91C1C",
    withoutGuard: "The nearby finding is coded as present.",
    withGuard: "The nearby finding is marked not present.",
    dataChange: "Assertion becomes absent for findings next to the trigger.",
  },
  POSSIBLE_EXISTENCE: {
    key: "POSSIBLE_EXISTENCE",
    title: "Possibly present",
    what: "Marks a nearby finding as possible, not confirmed.",
    why: "Notes say \"could be COPD\" or \"impression: tension headache\". That is a working guess.",
    ifWrong: "A possible diagnosis can look confirmed in the summary.",
    accent: "#B45309",
    withoutGuard: "The nearby finding is coded as confirmed.",
    withGuard: "The nearby finding is marked possible.",
    dataChange: "Assertion becomes possible for findings next to the trigger.",
  },
  HISTORICAL: {
    key: "HISTORICAL",
    title: "Historical",
    what: "Marks a nearby finding as past, not current.",
    why: "Notes say \"h/o hypertension\". That is history, not a new problem.",
    ifWrong: "An old problem can look current in the summary.",
    accent: "#1565C0",
    withoutGuard: "The nearby finding is coded as current.",
    withGuard: "The nearby finding is marked historical.",
    dataChange: "Assertion becomes historical for findings next to the trigger.",
  },
  PLANNED: {
    key: "PLANNED",
    title: "Planned",
    what: "Marks a test or appointment as booked, not done.",
    why: "Notes say \"awaiting colonoscopy\". The test is arranged, not completed.",
    ifWrong: "A booked test can look like it already happened.",
    accent: "#6A1B9A",
    withoutGuard: "The nearby procedure is coded as done.",
    withGuard: "The nearby procedure is marked planned, not done.",
    dataChange: "Assertion becomes planned for procedures next to the trigger.",
  },
  HYPOTHETICAL: {
    key: "HYPOTHETICAL",
    title: "Warning or advice",
    what: "Treats counselling lists as warnings, not current symptoms.",
    why: "Notes say \"side effects such as dizziness\". That is advice, not a finding.",
    ifWrong: "A warning can look like a current symptom.",
    accent: "#4527A0",
    withoutGuard: "The nearby symptom is coded as present.",
    withGuard: "The nearby symptom is marked as advice, not a current finding.",
    dataChange: "Assertion becomes hypothetical for findings next to the trigger.",
  },
  FAMILY: {
    key: "FAMILY",
    title: "Family member",
    what: "Links the finding to a relative, not the patient.",
    why: "Notes say \"fhx breast cancer\" or \"mum had bowel cancer\". That is the family.",
    ifWrong: "The patient can be coded with a relative's disease.",
    accent: "#00695C",
    withoutGuard: "The nearby finding is coded on the patient.",
    withGuard: "The nearby finding is marked as family history.",
    dataChange: "Assertion becomes family for findings next to the trigger.",
  },
  DECLINED: {
    key: "DECLINED",
    title: "Patient declined",
    what: "Marks an offered action as refused.",
    why: "Notes say \"declined referral\". The action did not happen.",
    ifWrong: "A refused referral can look like it was done.",
    accent: "#E65100",
    withoutGuard: "The nearby action is coded as done.",
    withGuard: "The nearby action is marked declined.",
    dataChange: "Assertion becomes declined for actions next to the trigger.",
  },
  CANCELLED: {
    key: "CANCELLED",
    title: "Missed or cancelled",
    what: "Marks an appointment or procedure as not done.",
    why: "Notes say \"did not attend\" or \"appointment cancelled\". No review took place.",
    ifWrong: "A missed clinic can look like a completed visit.",
    accent: "#546E7A",
    withoutGuard: "The nearby appointment is coded as completed.",
    withGuard: "The nearby appointment is marked as not done.",
    dataChange: "The event is not coded as completed.",
  },
};

export const CATEGORY_KEYS = Object.keys(CATEGORY_COPY);

export const CATEGORY_OPTIONS = CATEGORY_KEYS.map((key) => ({
  value: key,
  label: CATEGORY_COPY[key].title,
}));

export const DIRECTION_OPTIONS = [
  { value: "FORWARD", label: "After the phrase" },
  { value: "BACKWARD", label: "Before the phrase" },
  { value: "BIDIRECTIONAL", label: "Both sides" },
];

export function directionLabel(direction: string): string {
  if (direction === "FORWARD") return "Looks at words after the phrase";
  if (direction === "BACKWARD") return "Looks at words before the phrase";
  if (direction === "BIDIRECTIONAL") return "Looks at words on both sides";
  if (direction === "PSEUDO") return "Stops a nearby word from flipping the wrong thing";
  return direction;
}

export function scopeLabel(maxScope: number | null): string {
  if (maxScope == null) return "No word limit (special case)";
  if (maxScope === 1) return "Applies to 1 word nearby";
  return `Applies to ${maxScope} words nearby`;
}

export function categoryCopyFor(key: string): CategoryCopy {
  return CATEGORY_COPY[key] ?? {
    key,
    title: key,
    what: "Changes how nearby words are read.",
    why: "Some phrases flip meaning. This rule tells LEO how.",
    ifWrong: "A finding can get the wrong status.",
    accent: "#64748B",
    withoutGuard: "Nearby words keep their default meaning.",
    withGuard: "Nearby words get the status this rule sets.",
    dataChange: "Assertion is updated for findings next to the trigger.",
  };
}

function sampleNote(rule: ContextRule | null): string {
  if (!rule) return "";
  const raw = (rule.example || "").trim();
  if (!raw) return rule.literal;
  const parts = raw.split(/\s*(?:\u2192|->)\s*/);
  return (parts[0] || rule.literal).trim();
}

export function resolveContextExample(
  copy: CategoryCopy,
  rule: ContextRule | null,
): ContextWorkedExample {
  return {
    note: sampleNote(rule) || copy.why,
    withoutGuard: copy.withoutGuard,
    withGuard: copy.withGuard,
    dataChange: copy.dataChange,
  };
}
