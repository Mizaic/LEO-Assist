/**
 * Human-readable copy and recommended fix action for each failure_kind.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */

import type { WorkFixKind } from "./workFixApi";

export interface FailureCopy {
  /** Short headline shown at the top of the Debug pane. */
  headline: string;
  /** One-sentence explanation for the person. */
  detail: string;
  /** The Fix action to highlight as recommended. null = no recommendation. */
  recommendedFix: WorkFixKind | null;
}

const FAILURE_COPY: Record<string, FailureCopy> = {
  no_code: {
    headline: "No safe code yet",
    detail:
      "The system could not find a recognised clinical code for this phrase.",
    recommendedFix: "map",
  },
  wrong_kind: {
    headline: "Wrong kind of code",
    detail:
      "A code was found but it looks like the wrong type of thing. You may need to pick a better code.",
    recommendedFix: "map",
  },
  assertion_check: {
    headline: "Check if this is negated or historical",
    detail:
      "The phrase may be negated, past history, or about a family member. A context cue can help.",
    recommendedFix: "context",
  },
  unseen_form: {
    headline: "We have not seen this form before",
    detail:
      "The extraction was paused because this letter template is new or unusual. A teaching example will help.",
    recommendedFix: "teach",
  },
  new_phrase: {
    headline: "New phrase needs approval",
    detail: "A new surface form has been detected and is waiting for review.",
    recommendedFix: "map",
  },
  needs_gold_label: {
    headline: "Needs an expert label",
    detail: "This training example needs a verified gold-standard label.",
    recommendedFix: null,
  },
  safety_flag: {
    headline: "Safety alert",
    detail: "A safety net rule has flagged this case. Review and action it.",
    recommendedFix: null,
  },
  change_to_publish: {
    headline: "Change waiting to go live",
    detail:
      "Someone has drafted a fix. A different person must publish it before it goes live.",
    recommendedFix: null,
  },
};

const FALLBACK: FailureCopy = {
  headline: "",
  detail: "",
  recommendedFix: null,
};

export function getFailureCopy(kind: string | undefined): FailureCopy {
  return FAILURE_COPY[kind ?? ""] ?? FALLBACK;
}
