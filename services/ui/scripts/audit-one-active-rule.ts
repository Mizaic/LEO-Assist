/**
 * Focused audit for ONE approved AppropriatenessRule through the wizard
 * rehydration path (with shared-list + age-lift fixes).
 *
 * Usage:
 *   npx tsx scripts/audit-one-active-rule.ts scripts/active-rule-shards/1_1_2.json
 *
 * Explicit pass rules (fail the process on any breach):
 * 1. Tree loads after assignNodeIds + liftSharedPathwayDemographics.
 * 2. Multi-pathway with leaves opens at wizard step "review".
 * 3. Boundary count == pathway count.
 * 4. No fake "Situation A/B/..." placeholder labels.
 * 5. Tree-source boundaries paint zero situation highlights.
 * 6. No stacked same-start multi-colour highlights.
 * 7. Tree rehydration preserves OR pathway order.
 * 8. Tree-source pathways have zero unresolved text rows.
 * 9. Age (>=40/55/...} present on every pathway AND before lift must
 *    become a root Always-true DEMOGRAPHIC after lift (no duplicates
 *    left inside pathway ANDs).
 * 10. Shared quantifier lists (structure items attached to heuristic
 *     situations) must resolve AT_LEAST clusters with >=2 items on
 *     EVERY situation, not only the last one.
 * 11. Every Step 3 pathway row (and cluster child) must resolve to a
 *     leaf -- zero unresolved phrase-match gaps.
 */
import fs from "fs";

import { buildSituationBoundaryHighlights } from "../src/app/admin/guidance/EditRuleDialog/GuidelineQuotePanel";
import { buildInitialWizardState } from "../src/app/admin/guidance/EditRuleDialog/HighlightWizard/initialWizardState";
import {
  buildPathwayRows,
  buildRowResolver,
  countUnresolvedRows,
  orderPathwayNodesByBoundary,
  pathwayTextWindow,
  readMaterializedPathways,
} from "../src/app/admin/guidance/EditRuleDialog/HighlightWizard/wizardMapping";
import { liftSharedPathwayDemographics } from "../src/app/admin/guidance/EditRuleDialog/liftSharedPathwayDemographics";
import { findPathwaySplit } from "../src/app/admin/guidance/EditRuleDialog/pathwayDetection";
import {
  resolveAtLeastCluster,
  splitPathways,
} from "../src/app/admin/guidance/EditRuleDialog/SentenceEditor/pathwayTextSplit";
import { assignNodeIds } from "../src/app/admin/guidance/EditRuleDialog/treeOps";
import type { EditableLogicNode } from "../src/app/admin/guidance/EditRuleDialog/types";

interface RuleShard {
  name: string;
  rule_id: string;
  title?: string;
  recommendation_text: string;
  recommendation_structure: unknown;
  logic: Record<string, unknown>;
}

function demographicSig(node: EditableLogicNode): string | null {
  if (String(node.kind || "").toUpperCase() !== "DEMOGRAPHIC") return null;
  return [node.field, node.operator, String(node.value), String(node.unit ?? "")].join(
    "|",
  );
}

function collectPathwayDemographics(pathways: EditableLogicNode[]): string[][] {
  return pathways.map((p) => {
    if (String(p.kind || "").toUpperCase() !== "AND") return [];
    return (p.children ?? [])
      .map(demographicSig)
      .filter((s): s is string => Boolean(s));
  });
}

function audit(rule: RuleShard): { ok: boolean; issues: string[]; report: object } {
  const issues: string[] = [];
  const rawTree = assignNodeIds(rule.logic) as EditableLogicNode;
  const preSplit = findPathwaySplit(rawTree);
  const sharedBefore =
    preSplit && preSplit.prerequisites.length === 0
      ? (() => {
          const demos = collectPathwayDemographics(preSplit.orNode.children ?? []);
          if (demos.length < 2) return [] as string[];
          return demos[0].filter((sig) => demos.every((d) => d.includes(sig)));
        })()
      : [];

  const tree = liftSharedPathwayDemographics(rawTree);
  const state = buildInitialWizardState(
    tree,
    rule.recommendation_text,
    rule.recommendation_structure as never,
  );
  const split = findPathwaySplit(tree);
  const detected = splitPathways(
    rule.recommendation_text,
    rule.recommendation_structure as never,
  );

  if (sharedBefore.length > 0) {
    const prereqSigs = (split?.prerequisites ?? [])
      .map(demographicSig)
      .filter((s): s is string => Boolean(s));
    for (const sig of sharedBefore) {
      if (!prereqSigs.includes(sig)) {
        issues.push(`shared demographic ${sig} was not lifted to Always true`);
      }
    }
    for (const pathway of split?.orNode.children ?? []) {
      if (String(pathway.kind || "").toUpperCase() !== "AND") continue;
      for (const child of pathway.children ?? []) {
        const sig = demographicSig(child);
        if (sig && sharedBefore.includes(sig)) {
          issues.push(`shared demographic ${sig} still nested inside a pathway`);
        }
      }
    }
  }

  if (!split) {
    if (state.step !== "prerequisites") {
      issues.push(`single-situation expected prerequisites step, got ${state.step}`);
    }
    if (state.boundaries) {
      issues.push("single-situation should not carry pathway boundaries");
    }
    return {
      ok: issues.length === 0,
      issues,
      report: {
        title: rule.title,
        name: rule.name,
        rule_id: rule.rule_id,
        mode: "single",
        step: state.step,
        issues,
      },
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
    issues.push("fake Situation A-E placeholder labels");
  }
  if (detected && detected.length === pathways.length && source === "tree") {
    issues.push("text/structure matched pathway count but rehydration used tree");
  }
  if ((!detected || detected.length !== pathways.length) && source !== "tree") {
    issues.push(
      `mismatch text split (${detected?.length ?? 0}) vs pathways (${pathways.length}) source=${source}`,
    );
  }

  const highlights = buildSituationBoundaryHighlights(boundaries);
  if (source === "tree" && highlights.length > 0) {
    issues.push("tree boundaries must not paint situation highlights");
  }
  const starts = highlights.map((h) => h.start);
  if (starts.length > 1 && new Set(starts).size === 1) {
    issues.push(`stacked highlights all start at ${starts[0]}`);
  }

  const ordered = orderPathwayNodesByBoundary(
    pathways,
    boundaries,
    rule.recommendation_text,
  );
  if (source === "tree" && !ordered.every((n, i) => n === pathways[i])) {
    issues.push("tree rehydration scrambled pathway OR order");
  }

  // Shared quantifier list: every heuristic/structure boundary that
  // carries structureChildren must resolve a cluster with those items.
  const sharedListBoundaries = (detected ?? []).filter(
    (b) => (b.structureChildren?.length ?? 0) >= 2,
  );
  if (sharedListBoundaries.length >= 2) {
    for (let i = 0; i < sharedListBoundaries.length; i++) {
      const cluster = resolveAtLeastCluster(sharedListBoundaries[i]);
      if (!cluster || cluster.items.length < 2) {
        issues.push(
          `shared-list situation ${i} missing AT_LEAST cluster items (got ${cluster?.items.length ?? 0})`,
        );
      }
    }
  }

  const materialized = readMaterializedPathways(tree, boundaries.length);
  let unresolvedTotal = 0;
  const pathwaySummaries: object[] = [];
  materialized.forEach((pathwayNode, index) => {
    const boundary = boundaries[index];
    if (!boundary) return;
    const rows = buildPathwayRows(boundary);
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
    const unresolved = countUnresolvedRows(rows.items, resolver);
    unresolvedTotal += unresolved;
    if (unresolved > 0) {
      issues.push(
        `pathway ${index}: ${unresolved} unresolved row(s) after rehydration`,
      );
    }
    const atLeast = (pathwayNode.children ?? []).filter(
      (c) => String(c.kind || "").toUpperCase() === "AT_LEAST",
    );
    pathwaySummaries.push({
      index,
      source: boundary.source,
      rowCount: rows.items.length,
      hasCluster: rows.hasCluster,
      structureChildren: boundary.structureChildren?.length ?? 0,
      unresolved,
      atLeastMins: atLeast.map((n) => n.min ?? null),
      leafKinds: (pathwayNode.children ?? []).map((c) => c.kind),
    });
  });

  return {
    ok: issues.length === 0,
    issues,
    report: {
      title: rule.title,
      name: rule.name,
      rule_id: rule.rule_id,
      mode: "multi",
      step: state.step,
      pathwayCount: pathways.length,
      boundarySource: source,
      textSplitCount: detected?.length ?? null,
      highlightSpans: highlights.length,
      unresolvedTotal,
      prerequisites: (split.prerequisites ?? []).map((p) => ({
        kind: p.kind,
        field: p.field,
        operator: p.operator,
        value: p.value,
      })),
      pathways: pathwaySummaries,
      issues,
    },
  };
}

const shardPath = process.argv[2];
if (!shardPath) {
  console.error("Usage: npx tsx scripts/audit-one-active-rule.ts <shard.json>");
  process.exit(2);
}
const rule = JSON.parse(fs.readFileSync(shardPath, "utf8")) as RuleShard;
const result = audit(rule);
console.log(JSON.stringify(result.report, null, 2));
if (!result.ok) {
  console.error(`FAIL ${rule.title || rule.name}: ${result.issues.join("; ")}`);
  process.exit(1);
}
console.error(`PASS ${rule.title || rule.name}`);
process.exit(0);
