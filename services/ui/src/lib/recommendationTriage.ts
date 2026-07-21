/**
 * Client-side mirror of libs/guidance/recommendation_triage.py.
 * Used to pre-select ruleable recommendations in the picker.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export type TriageBucket = "full_rule" | "trigger_plus_narrative" | "no_rule";

const REFERRAL_RE =
  /\b(refer|referral|urgent(?:ly)?|same[- ]day|2[- ]?ww|two[- ]week|investigate|offer\s+(?:a\s+)?(?:test|scan|imaging|blood)|consider\s+(?:a\s+)?(?:referral|CT|MRI|ultrasound|colonoscopy)|arrange|admit|hospital)\b/i;

const ADVICE_ACTION_RE =
  /\b(advise|advice|discuss|information|inform|explain|counsel|encourage|support|educat|lifestyle|diet|skin\s+care|moisturis|make-up|makeup|sunscreen|syndet|cleanser|picking|scratching)\b/i;

const INFO_ONLY_RE =
  /\b(give\s+people\s+.*\s+information|include\s+parents\s+and\s+carers|topics\s+to\s+cover|there\s+is\s+not\s+enough\s+evidence|for\s+general\s+advice)\b/i;

const CLINICAL_TRIGGER_RE =
  /\b(people\s+with|person\s+with|patients?\s+with|diagnos|symptom|sign|lesion|severity|moderate|severe|fulminans|suspected|confirmed|aged|years)\b/i;

export function triageRecommendation(verbatim: string): TriageBucket {
  const text = (verbatim || "").trim();
  if (!text) return "no_rule";

  const hasReferral = REFERRAL_RE.test(text);
  const hasAdvice = ADVICE_ACTION_RE.test(text);
  const infoOnly = INFO_ONLY_RE.test(text);
  const hasTrigger = CLINICAL_TRIGGER_RE.test(text);

  if (infoOnly && !hasReferral) return "no_rule";
  if (hasReferral) return "full_rule";
  if (hasTrigger && hasAdvice) return "trigger_plus_narrative";
  if (hasAdvice && !hasTrigger) return "no_rule";
  if (hasTrigger) return "trigger_plus_narrative";
  return "no_rule";
}

export function defaultSelectedForTriage(bucket: TriageBucket): boolean {
  return bucket === "full_rule" || bucket === "trigger_plus_narrative";
}
