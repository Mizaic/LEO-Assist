/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * "Does this highlighted phrase read as an age or sex restriction?" --
 * the forward direction of `leafTextMatch.ts`'s `demographicMatchCandidate`
 * (which goes DEMOGRAPHIC node -> guideline wording). This module goes the
 * other way: guideline wording -> a DEMOGRAPHIC node's field/operator/value.
 *
 * Without this, highlighting a plain-English age phrase like "aged 40 and
 * over" fell through to the generic SNOMED concept search, which can only
 * ever surface a bare "current age" observable concept -- not the
 * operator/threshold the rule actually needs, and picking it added nothing
 * useful. Age and sex are always answered with a DEMOGRAPHIC leaf's
 * operator/value/unit fields, never a SNOMED code, so any selection that
 * reads as one of these phrasings must be routed to the same inline
 * age/sex editor the "+ Add age" / "+ Add sex" buttons already open --
 * see `handleRequestAdd`'s call site for the routing decision.
 *
 * Deliberately conservative, matching this file family's established
 * style (`looksLikeLeadOrCluster`, `looksLikeWithAnd` in
 * `SentenceEditor/pathwayTextSplit.ts`): a match is only returned when the
 * matched phrase accounts for nearly the WHOLE selection, so a longer
 * highlighted span that happens to contain a number or the word "male"
 * alongside an unrelated finding is left alone rather than mis-routed.
 */

export interface DemographicPhraseMatch {
  field: "age" | "sex";
  operator: string;
  value: string;
  value2?: string;
  unit: string | null;
}

const AGE_RANGE_RE = /\baged?\s+(\d{1,3})\s*(?:to|-)\s*(\d{1,3})\b/i;
const AGE_AND_OVER_RE =
  /\b(?:aged?\s+(\d{1,3})|(\d{1,3})\s+years?)\s*(?:and|or)\s+(?:over|older|above)\b/i;
const AGE_OVER_RE = /\b(?:aged?\s+over|over\s+the\s+age\s+of)\s+(\d{1,3})\b/i;
const AGE_UNDER_RE = /\b(?:aged?\s+under|under\s+the\s+age\s+of)\s+(\d{1,3})\b/i;
const AGE_BARE_RE = /\baged?\s+(\d{1,3})\b/i;

const SEX_WORDS: Record<string, "male" | "female"> = {
  men: "male",
  man: "male",
  male: "male",
  males: "male",
  boys: "male",
  boy: "male",
  women: "female",
  woman: "female",
  female: "female",
  females: "female",
  girls: "female",
  girl: "female",
};
const SEX_RE = new RegExp(`\\b(${Object.keys(SEX_WORDS).join("|")})\\b`, "i");

/** True when `match` (the regexp's own `[0]`) accounts for nearly all of
 *  `trimmed` -- see this file's doc comment on why that guard exists. */
function matchIsWholeSelection(trimmed: string, match: string): boolean {
  const remainder = trimmed.replace(match, "").trim();
  return remainder.length <= 3;
}

function detectAgePhrase(trimmed: string): DemographicPhraseMatch | null {
  const range = AGE_RANGE_RE.exec(trimmed);
  if (range && matchIsWholeSelection(trimmed, range[0])) {
    return { field: "age", operator: "between", value: range[1], value2: range[2], unit: "years" };
  }

  const andOver = AGE_AND_OVER_RE.exec(trimmed);
  if (andOver && matchIsWholeSelection(trimmed, andOver[0])) {
    return { field: "age", operator: ">=", value: andOver[1] ?? andOver[2], unit: "years" };
  }

  const over = AGE_OVER_RE.exec(trimmed);
  if (over && matchIsWholeSelection(trimmed, over[0])) {
    return { field: "age", operator: ">", value: over[1], unit: "years" };
  }

  const under = AGE_UNDER_RE.exec(trimmed);
  if (under && matchIsWholeSelection(trimmed, under[0])) {
    return { field: "age", operator: "<", value: under[1], unit: "years" };
  }

  const bare = AGE_BARE_RE.exec(trimmed);
  if (bare && matchIsWholeSelection(trimmed, bare[0])) {
    return { field: "age", operator: "=", value: bare[1], unit: "years" };
  }

  return null;
}

function detectSexPhrase(trimmed: string): DemographicPhraseMatch | null {
  const match = SEX_RE.exec(trimmed);
  if (!match || !matchIsWholeSelection(trimmed, match[0])) return null;
  const value = SEX_WORDS[match[1].toLowerCase()];
  return { field: "sex", operator: "=", value, unit: null };
}

/**
 * Classifies a highlighted phrase as an age or sex restriction, or
 * returns null when it reads as an ordinary finding/procedure that
 * should still go through SNOMED concept search.
 */
export function detectDemographicPhrase(text: string): DemographicPhraseMatch | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return detectAgePhrase(trimmed) ?? detectSexPhrase(trimmed);
}
