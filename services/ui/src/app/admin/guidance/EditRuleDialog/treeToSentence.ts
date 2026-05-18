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
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import { friendlyTerm } from "./copy";
import type { EditableLogicNode } from "./types";

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

const AGE_OPERATORS: Record<string, (v: string, unit: string) => string> = {
  ">=": (v, u) => `${v} ${u} or older`,
  "<=": (v, u) => `${v} ${u} or younger`,
  ">": (v, u) => `over ${v} ${u}`,
  "<": (v, u) => `under ${v} ${u}`,
  "=": (v, u) => `exactly ${v} ${u}`,
};

const SEX_VALUES: Record<string, string> = {
  male: "male",
  female: "female",
  m: "male",
  f: "female",
};

function demographicToText(node: EditableLogicNode): string {
  const field = node.field ?? "age";
  const op = node.operator ?? "=";
  const value = String(node.value ?? "");
  const unit = node.unit ?? "";
  if (!value) return "is a patient with an unfilled detail";
  if (field === "age") {
    const fmt = AGE_OPERATORS[op] ?? ((v: string, u: string) => `${op} ${v} ${u}`);
    return `is ${fmt(value, unit || "years")}`;
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

function conceptText(node: EditableLogicNode, resolve?: TermResolver): string {
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

function leafToCondition(
  node: EditableLogicNode,
  resolve?: TermResolver,
): string {
  if (node.kind === "DEMOGRAPHIC") return demographicToText(node);
  if (node.kind === "CONCEPT") return `has ${conceptText(node, resolve)}`;
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
      lead: "This rule has no conditions yet. Add a symptom or patient detail to get started.",
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
