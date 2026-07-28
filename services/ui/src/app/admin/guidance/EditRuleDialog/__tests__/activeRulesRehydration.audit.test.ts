/**
 * Logic audit: every active AppropriatenessRule rehydrates into the
 * highlight wizard without the table-driven / fake-Situation failure
 * mode (stacked prefix highlights + blocked "needs a match" rows).
 *
 * Fixture regenerated from Neo4j active rules via MCP.
 */
import fs from "fs";
import path from "path";

import { buildSituationBoundaryHighlights } from "../GuidelineQuotePanel";
import { buildInitialWizardState } from "../HighlightWizard/initialWizardState";
import {
  buildPathwayRows,
  buildRowResolver,
  countUnresolvedRows,
  orderPathwayNodesByBoundary,
  pathwayTextWindow,
  readMaterializedPathways,
} from "../HighlightWizard/wizardMapping";
import { liftSharedPathwayDemographics } from "../liftSharedPathwayDemographics";
import { findPathwaySplit } from "../pathwayDetection";
import { splitPathways } from "../SentenceEditor/pathwayTextSplit";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";

interface ActiveRuleFixture {
  name: string;
  rule_id: string;
  recommendation_text: string;
  recommendation_structure: Parameters<typeof buildInitialWizardState>[2];
  logic: Record<string, unknown>;
}

const FIXTURE = path.join(
  __dirname,
  "fixtures",
  "activeRulesRehydration.json",
);

function loadRules(): ActiveRuleFixture[] {
  return JSON.parse(fs.readFileSync(FIXTURE, "utf8")) as ActiveRuleFixture[];
}

type AuditRow = {
  name: string;
  mode: "single" | "multi";
  step: string;
  pathwayCount: number;
  boundarySource: string | null;
  textSplitCount: number | null;
  highlightSpans: number;
  unresolvedTotal: number;
  issues: string[];
};

function auditRule(rule: ActiveRuleFixture): AuditRow {
  const tree = liftSharedPathwayDemographics(
    assignNodeIds(rule.logic) as EditableLogicNode,
  );
  const state = buildInitialWizardState(
    tree,
    rule.recommendation_text,
    rule.recommendation_structure,
  );
  const split = findPathwaySplit(tree);
  const detected = splitPathways(
    rule.recommendation_text,
    rule.recommendation_structure,
  );
  const issues: string[] = [];

  if (!split) {
    if (state.step !== "prerequisites") {
      issues.push(`expected prerequisites for single-situation, got ${state.step}`);
    }
    if (state.boundaries) {
      issues.push("single-situation should not carry pathway boundaries");
    }
    return {
      name: rule.name,
      mode: "single",
      step: state.step,
      pathwayCount: 0,
      boundarySource: null,
      textSplitCount: detected?.length ?? null,
      highlightSpans: 0,
      unresolvedTotal: 0,
      issues,
    };
  }

  const pathways = split.orNode.children ?? [];
  const boundaries = state.boundaries ?? [];
  const source = boundaries[0]?.source ?? null;

  if (state.step !== "review") {
    issues.push(`multi-pathway with leaves should open at review, got ${state.step}`);
  }
  if (boundaries.length !== pathways.length) {
    issues.push(
      `boundary count ${boundaries.length} != pathway count ${pathways.length}`,
    );
  }
  if (boundaries.some((b) => /^Situation [A-Z]$/.test(b.text))) {
    issues.push("still using fake Situation A-E placeholder labels");
  }
  if (
    detected &&
    detected.length === pathways.length &&
    source === "tree"
  ) {
    issues.push("text/structure split matched but rehydration used tree source");
  }
  if (
    (!detected || detected.length !== pathways.length) &&
    source !== "tree"
  ) {
    issues.push(
      `mismatch text split (${detected?.length ?? 0}) vs pathways (${pathways.length}) but source=${source}`,
    );
  }

  const highlights = buildSituationBoundaryHighlights(boundaries);
  if (source === "tree" && highlights.length > 0) {
    issues.push("tree boundaries must not paint situation highlights");
  }
  // Stacked same-start multi-colour paints (the 1.5.9 bug).
  const starts = highlights.map((h) => h.start);
  if (starts.length > 1 && new Set(starts).size === 1) {
    issues.push(`stacked highlights all start at ${starts[0]}`);
  }

  const ordered = orderPathwayNodesByBoundary(
    pathways,
    boundaries,
    rule.recommendation_text,
  );
  if (source === "tree") {
    const sameOrder = ordered.every((n, i) => n === pathways[i]);
    if (!sameOrder) {
      issues.push("tree rehydration scrambled pathway OR order");
    }
  }

  const materialized = readMaterializedPathways(tree, boundaries.length);
  let unresolvedTotal = 0;
  materialized.forEach((pathwayNode, index) => {
    const boundary = boundaries[index];
    if (!boundary) return;
    const { items } = buildPathwayRows(boundary);
    const window = pathwayTextWindow(
      boundaries,
      index,
      rule.recommendation_text.length,
    );
    const resolver = buildRowResolver(
      pathwayNode,
      rule.recommendation_text,
      window,
    );
    const unresolved = countUnresolvedRows(items, resolver);
    unresolvedTotal += unresolved;
    if (unresolved > 0) {
      issues.push(
        `pathway ${index}: ${unresolved} unresolved row(s) after rehydration`,
      );
    }
  });

  return {
    name: rule.name,
    mode: "multi",
    step: state.step,
    pathwayCount: pathways.length,
    boundarySource: source,
    textSplitCount: detected?.length ?? null,
    highlightSpans: highlights.length,
    unresolvedTotal,
    issues,
  };
}

describe("active approved rules rehydration audit", () => {
  const rules = loadRules();

  it("loads the fixture of active rules", () => {
    expect(rules.length).toBeGreaterThanOrEqual(20);
  });

  it("rehydrates every active rule without known failure modes", () => {
    const rows = rules.map(auditRule);
    const failed = rows.filter((r) => r.issues.length > 0);

    // eslint-disable-next-line no-console
    console.log(
      JSON.stringify(
        {
          total: rows.length,
          single: rows.filter((r) => r.mode === "single").length,
          multi: rows.filter((r) => r.mode === "multi").length,
          bySource: {
            tree: rows.filter((r) => r.boundarySource === "tree").length,
            heuristic: rows.filter((r) => r.boundarySource === "heuristic").length,
            structure: rows.filter((r) => r.boundarySource === "structure").length,
            none: rows.filter((r) => r.boundarySource === null).length,
          },
          rows: rows.map((r) => ({
            name: r.name,
            mode: r.mode,
            pathways: r.pathwayCount || undefined,
            source: r.boundarySource,
            textSplit: r.textSplitCount,
            highlights: r.highlightSpans,
            unresolved: r.unresolvedTotal,
            ok: r.issues.length === 0,
            issues: r.issues,
          })),
        },
        null,
        2,
      ),
    );

    expect(failed).toEqual([]);
  });
});
