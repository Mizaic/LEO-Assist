/**
 * Render a rule logic tree into a human-readable summary.
 *
 * The summary is shown above the editor so a clinician with average
 * reading age (UK 9-11) can understand what the rule means without
 * walking the tree. The renderer is fully deterministic and pure so it
 * can be tested in isolation; an LLM-backed alternative lives in
 * Phase 4 / DI-LEO-AI-155.
 *
 * Returns a structured ``RuleSummary`` so the SummaryCard can render
 * a lead sentence followed by an optional bullet list of pathways.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import { OBSERVATION_MODE_LABELS, friendlyTerm, recencyLabel } from "./copy";
import type {
  EditableLogicNode,
  EditableObservationPayload,
} from "./types";

export interface PathwaySummary {
  /** Connector word ("" for the first pathway, "or" thereafter). */
  connector: string;
  /** Short headline for this pathway. */
  headline: string;
  /** Each condition as a sub-sentence ("has cough", "is a smoker"). */
  conditions: string[];
}

export interface RuleSummary {
  /** Primary sentence shown in the summary card. */
  lead: string;
  /** Optional alternative routes when the tree has an OR branch. */
  pathways?: PathwaySummary[];
  /** Whether the renderer recognised the tree shape; false means we
   * fell back to a generic flat join. */
  isWellShaped: boolean;
}

const AGE_OPERATORS: Record<string, (v: string, unit: string, v2?: string) => string> = {
  ">=": (v, u) => `${v} ${u} or older`,
  "<=": (v, u) => `${v} ${u} or younger`,
  ">": (v, u) => `over ${v} ${u}`,
  "<": (v, u) => `under ${v} ${u}`,
  "=": (v, u) => `exactly ${v} ${u}`,
  "between": (v, u, v2) => v2 ? `aged ${v}\u2013${v2} ${u}`.replace(" years", " years").trimEnd() : `aged ${v}+ ${u}`,
};

const SEX_VALUES: Record<string, string> = {
  male: "male",
  female: "female",
  m: "male",
  f: "female",
};

/**
 * Exported so the SentenceEditor canvas (fill-in-the-blank prose
 * builder) can reuse the exact same wording as this read-only
 * preview instead of duplicating the phrasing rules. Pure
 * export-visibility change; behaviour is unchanged.
 */
export function demographicToText(node: EditableLogicNode): string {
  const field = node.field ?? "age";
  const op = node.operator ?? "=";
  const value = String(node.value ?? "");
  const value2 = node.value2 != null ? String(node.value2) : undefined;
  const unit = node.unit ?? "";
  if (!value) return "is a patient with an unfilled detail";
  if (field === "age") {
    const fmt = AGE_OPERATORS[op] ?? ((v: string, u: string) => `${op} ${v} ${u}`);
    return `is ${fmt(value, unit || "years", value2)}`;
  }
  if (field === "sex") {
    return `is ${SEX_VALUES[value.toLowerCase()] ?? value}`;
  }
  return `has ${field} ${op} ${value} ${unit}`.trim();
}

/**
 * Lookup map from SNOMED concept id to a plain-English term.
 * The popover passes one in built from the recent SNOMED searches so the
 * exclusion list can render as ", except trial of smoking" instead of
 * ", except code 266920004".
 */
export type TermResolver = (conceptId: string) => string | undefined;

export function conceptText(node: EditableLogicNode, resolve?: TermResolver): string {
  const c = node.criterion;
  const seeds = c?.seeds ?? [];
  const exclusions = c?.excluded_concept_ids ?? [];

  // Legacy single-seed shape (or empty seeds): use the headline term.
  if (seeds.length === 0) {
    const term = friendlyTerm(c?.preferred_term);
    return term.toLowerCase() || "an unfilled symptom";
  }

  let body: string;
  if (seeds.length === 1) {
    const term = friendlyTerm(seeds[0].preferred_term).toLowerCase();
    body =
      seeds[0].include_descendants !== false
        ? `${term} (or any kind of ${term})`
        : term;
  } else {
    const allIncludeDescendants = seeds.every(
      (s) => s.include_descendants !== false,
    );
    const terms = seeds.map((s) =>
      friendlyTerm(s.preferred_term).toLowerCase(),
    );
    if (allIncludeDescendants) {
      const primaryTerm = friendlyTerm(c?.preferred_term).toLowerCase();
      body = `${primaryTerm} (or any kind of: ${terms.join(", ")})`;
    } else {
      body = `one of: ${terms.join(", ")}`;
    }
  }

  if (exclusions.length === 0) return body;

  const labels = exclusions.map((id) => {
    const term = resolve?.(id);
    return term ? friendlyTerm(term).toLowerCase() : `code ${id}`;
  });
  const tail =
    labels.length === 1
      ? labels[0]
      : `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  return `${body}, except ${tail}`;
}

/**
 * Every seed's own friendly term, for surfaces that need to render a
 * multi-seed CONCEPT leaf as a scannable list of individual findings
 * instead of one packed "one of: a, b, c, ..." sentence -- see
 * StepPrerequisites's "Captured so far" panel. Falls back to the
 * single legacy preferred_term when there are no seeds.
 */
export function conceptSeedLabels(node: EditableLogicNode): string[] {
  const c = node.criterion;
  const seeds = c?.seeds ?? [];
  if (seeds.length === 0) {
    const term = friendlyTerm(c?.preferred_term);
    return term ? [term] : [];
  }
  return seeds.map((s) => friendlyTerm(s.preferred_term));
}

/** Strip descendant-expansion / exclusion tails so subject rewrites
 *  match the clinical finding itself. */
function conceptCoreTerm(body: string): string {
  return body
    .toLowerCase()
    .replace(/\s*\(or any kind of[^)]*\)\s*$/i, "")
    .replace(/, except .+$/i, "")
    .trim();
}

/**
 * SNOMED terms like "Parental concern about child" already name a
 * third party. Wrapping them as "has parental concern about child"
 * makes the patient sound like the concerned parent. Reword so the
 * record meaning stays clear: a parent is concerned about this patient.
 */
function rewriteThirdPartyConceptClause(body: string): string | null {
  const core = conceptCoreTerm(body);
  if (
    core === "parental concern" ||
    /\bparental concern about (?:the )?child\b/.test(core)
  ) {
    return "has a parent who is concerned about them";
  }
  if (/\bparental anxiety\b/.test(core)) {
    return "has a parent who is anxious about their symptoms";
  }
  return null;
}

/**
 * CONCEPT leaf as a patient-condition clause ("has cough", or a
 * rewritten third-party finding). Shared by the live preview and the
 * highlight wizard's "Captured so far" labels.
 */
export function conceptConditionClause(
  node: EditableLogicNode,
  resolve?: TermResolver,
): string {
  const body = conceptText(node, resolve);
  return rewriteThirdPartyConceptClause(body) ?? `has ${body}`;
}

function listOfConcepts(
  nodes: EditableLogicNode[],
  resolve?: TermResolver,
): string {
  const items = nodes.map((n) => conceptText(n, resolve));
  return joinWithLast(items, "or");
}

function joinWithLast(items: string[], lastSep: "and" | "or"): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} ${lastSep} ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, ${lastSep} ${items[items.length - 1]}`;
}

function observationOperatorText(op: string): string {
  switch (op) {
    case ">=":
      return "at least";
    case "<=":
      return "at most";
    case ">":
      return "more than";
    case "<":
      return "less than";
    case "=":
      return "exactly";
    case "between":
      return "between";
    default:
      return op;
  }
}

export function observationToText(obs: EditableObservationPayload): string {
  const term = friendlyTerm(obs.observable_term).toLowerCase() || "a lab value";

  // Advanced modes are summarised softly so clinicians see the shape
  // without pretending the canvas can edit them inline.
  if (obs.temporal) {
    return `has ${term} with a timing rule (${OBSERVATION_MODE_LABELS.temporal.toLowerCase()})`;
  }
  if (obs.reference_range) {
    return `has ${term} outside the expected range for the patient`;
  }
  if (obs.trend) {
    return `has ${term} with a trend check across readings`;
  }
  if (obs.aggregation) {
    return `has ${term} with an average or running summary`;
  }

  const opWord = observationOperatorText(obs.operator ?? ">=");
  const unit = obs.unit ? ` ${obs.unit}` : "";
  let valueText: string;
  if (Array.isArray(obs.value)) {
    const [lo, hi] = obs.value;
    valueText = `${lo} and ${hi}${unit}`;
  } else {
    valueText = `${obs.value ?? "?"}${unit}`;
  }
  const recency = recencyLabel(obs.within_days).toLowerCase();
  return `has ${term} ${opWord} ${valueText} ${recency}`.trim();
}

function leafToCondition(
  node: EditableLogicNode,
  resolve?: TermResolver,
): string {
  if (node.kind === "DEMOGRAPHIC") return demographicToText(node);
  if (node.kind === "CONCEPT") return conceptConditionClause(node, resolve);
  if (node.kind === "OBSERVATION") {
    return node.observation
      ? observationToText(node.observation)
      : "has a lab value that still needs to be filled in";
  }
  if (node.kind === "RULE_FIRED") {
    const name = node.display_name || node.referenced_rule_id || "another rule";
    return node.outcome === "not_fired"
      ? `did NOT meet the criteria for "${name}"`
      : `already meets the criteria for "${name}"`;
  }
  if (node.kind === "AT_LEAST") {
    const concepts = (node.children ?? []).filter((c) => c.kind === "CONCEPT");
    const list = listOfConcepts(concepts, resolve);
    return `has at least ${node.min ?? 1} of: ${list}`;
  }
  if (node.kind === "NOT") {
    const inner = node.children?.[0];
    return inner
      ? `does NOT have ${stripVerbPrefix(leafToCondition(inner, resolve))}`
      : "(empty NOT)";
  }
  // Nested AND / OR: render compactly inline
  const parts = (node.children ?? []).map((c) => leafToCondition(c, resolve));
  const sep = node.kind === "AND" ? "and" : "or";
  return joinWithLast(parts, sep);
}

function stripVerbPrefix(text: string): string {
  return text
    .replace(/^is\s+/i, "")
    .replace(/^has\s+/i, "")
    .replace(/^does\s+(?:not\s+)?have\s+/i, "");
}

function pathwayConditions(
  node: EditableLogicNode,
  resolve?: TermResolver,
): string[] {
  if (node.kind === "AND") {
    return (node.children ?? []).map((c) => leafToCondition(c, resolve));
  }
  return [leafToCondition(node, resolve)];
}

function pathwayHeadline(node: EditableLogicNode, index: number): string {
  // Phase 2 of the wizard redesign: a group node may carry an
  // optional plain-English ``name``. When set, use it verbatim so the
  // pathway card title actually means something. Otherwise fall back
  // to the positional letter so legacy data still renders.
  const named = typeof node.name === "string" ? node.name.trim() : "";
  if (named) return named;
  if (index === 0) return "Pathway A";
  return `Pathway ${String.fromCharCode(65 + index)}`;
}

/**
 * Render the tree to a structured summary. Recognises the common
 * shape ``AND[Demographics..., OR[pathway1, pathway2, ...]]`` and
 * splits it into a lead sentence + pathway list. Other shapes fall
 * back to a single sentence.
 */
export function treeToSentence(
  node: EditableLogicNode | null,
  resolve?: TermResolver,
): RuleSummary {
  if (!node) {
    return {
      lead: "This rule has no conditions yet. Add a symptom, procedure, situation, or patient detail to get started.",
      isWellShaped: false,
    };
  }

  // Common pathway shape: AND[Demo*, OR[...pathways]]
  if (node.kind === "AND") {
    const children = node.children ?? [];
    const demos = children.filter((c) => c.kind === "DEMOGRAPHIC");
    const orChildren = children.filter((c) => c.kind === "OR");
    const otherCount = children.length - demos.length - orChildren.length;

    if (orChildren.length === 1 && otherCount === 0) {
      const orChild = orChildren[0];
      const demoText = joinWithLast(
        demos.map((d) => leafToCondition(d, resolve)),
        "and",
      );
      const lead = demoText
        ? `Applies to patients who ${demoText}, AND match one of these pathways:`
        : "Applies to patients who match any of these pathways:";
      const pathways: PathwaySummary[] = (orChild.children ?? []).map((p, i) => ({
        connector: i === 0 ? "" : "OR",
        headline: pathwayHeadline(p, i),
        conditions: pathwayConditions(p, resolve),
      }));
      return { lead, pathways, isWellShaped: true };
    }

    // Flat AND of leaves
    const allParts = children.map((c) => leafToCondition(c, resolve));
    return {
      lead: `Applies to patients who ${joinWithLast(allParts, "and")}.`,
      isWellShaped: true,
    };
  }

  if (node.kind === "OR") {
    const pathways: PathwaySummary[] = (node.children ?? []).map((p, i) => ({
      connector: i === 0 ? "" : "OR",
      headline: pathwayHeadline(p, i),
      conditions: pathwayConditions(p, resolve),
    }));
    return {
      lead: "Applies to patients who match any of these pathways:",
      pathways,
      isWellShaped: true,
    };
  }

  return {
    lead: `Applies to patients who ${leafToCondition(node, resolve)}.`,
    isWellShaped: true,
  };
}
