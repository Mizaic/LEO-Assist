/**
 * One-shot audit: pending NG12 rules vs highlight-wizard rehydration.
 * Run: npx tsx scripts/audit-pending-ng12-rehydration.ts
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import fs from "fs";
import path from "path";

import { buildSituationBoundaryHighlights } from "../src/app/admin/guidance/EditRuleDialog/GuidelineQuotePanel";
import { buildInitialWizardState } from "../src/app/admin/guidance/EditRuleDialog/HighlightWizard/initialWizardState";
import {
  buildPathwayRows,
  buildRowResolver,
  countUnresolvedRows,
  orderPathwayNodesByBoundary,
  readMaterializedPathways,
} from "../src/app/admin/guidance/EditRuleDialog/HighlightWizard/wizardMapping";
import { findPathwaySplit } from "../src/app/admin/guidance/EditRuleDialog/pathwayDetection";
import { splitPathways } from "../src/app/admin/guidance/EditRuleDialog/SentenceEditor/pathwayTextSplit";
import { assignNodeIds } from "../src/app/admin/guidance/EditRuleDialog/treeOps";
import type { EditableLogicNode } from "../src/app/admin/guidance/EditRuleDialog/types";

interface PendingRule {
  name: string;
  rule_id: string;
  generation_outcome: string;
  needs_human_review: boolean;
  recommendation_text: string;
  recommendation_structure: unknown;
  logic: Record<string, unknown>;
  has_action: boolean;
  verifier_json: string;
}

const LEAF = new Set(["CONCEPT", "DEMOGRAPHIC", "OBSERVATION"]);

function countLeaves(node: EditableLogicNode): number {
  const kind = String(node.kind || "").toUpperCase();
  if (LEAF.has(kind)) return 1;
  return (node.children ?? []).reduce((n, c) => n + countLeaves(c), 0);
}

function isEmptyTree(node: EditableLogicNode): boolean {
  return countLeaves(node) === 0;
}

type Bucket =
  | "ready_review"
  | "ready_single"
  | "table_tree_ok"
  | "rehydrates_but_conditions_gap"
  | "empty_or_no_leaves"
  | "broken_rehydration"
  | "non_codable_signal";

function classify(rule: PendingRule): {
  bucket: Bucket;
  issues: string[];
  mode: "single" | "multi" | "empty";
  pathwayCount: number;
  boundarySource: string | null;
  unresolved: number;
  leafCount: number;
} {
  const issues: string[] = [];
  const verifier = (rule.verifier_json || "").toLowerCase();
  if (
    verifier.includes("non_codable") ||
    verifier.includes("no_rule") ||
    rule.generation_outcome.toLowerCase().includes("no_rule")
  ) {
    issues.push("verifier/outcome marks non-codable or no_rule");
  }

  const tree = assignNodeIds(rule.logic) as EditableLogicNode;
  const leafCount = countLeaves(tree);
  if (isEmptyTree(tree)) {
    return {
      bucket: issues.length ? "non_codable_signal" : "empty_or_no_leaves",
      issues: [...issues, "logic tree has no CONCEPT/DEMOGRAPHIC/OBSERVATION leaves"],
      mode: "empty",
      pathwayCount: 0,
      boundarySource: null,
      unresolved: 0,
      leafCount,
    };
  }

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

  if (!split) {
    if (state.step !== "prerequisites") {
      issues.push(`single-situation opened at ${state.step}, expected prerequisites`);
    }
    if (state.boundaries) issues.push("single-situation carried pathway boundaries");
    return {
      bucket: issues.length ? "broken_rehydration" : "ready_single",
      issues,
      mode: "single",
      pathwayCount: 0,
      boundarySource: null,
      unresolved: 0,
      leafCount,
    };
  }

  const pathways = split.orNode.children ?? [];
  const boundaries = state.boundaries ?? [];
  const source = boundaries[0]?.source ?? null;

  if (state.step !== "review" && pathways.every((p) => countLeaves(p) > 0)) {
    issues.push(`filled multi-pathway opened at ${state.step}, expected review`);
  }
  if (boundaries.length !== pathways.length) {
    issues.push(
      `boundary count ${boundaries.length} != pathway count ${pathways.length}`,
    );
  }
  if (boundaries.some((b) => /^Situation [A-Z]$/.test(b.text))) {
    issues.push("fake Situation A-E placeholders");
  }
  if (
    (!detected || detected.length !== pathways.length) &&
    source !== "tree" &&
    pathways.every((p) => countLeaves(p) > 0)
  ) {
    issues.push(
      `text/structure split ${detected?.length ?? 0} vs pathways ${pathways.length} without tree fallback`,
    );
  }

  const highlights = buildSituationBoundaryHighlights(boundaries);
  if (source === "tree" && highlights.length > 0) {
    issues.push("tree boundaries painted situation highlights");
  }
  const starts = highlights.map((h) => h.start);
  if (starts.length > 1 && new Set(starts).size === 1) {
    issues.push(`stacked highlights at offset ${starts[0]}`);
  }

  const ordered = orderPathwayNodesByBoundary(
    pathways,
    boundaries,
    rule.recommendation_text,
  );
  if (source === "tree" && !ordered.every((n, i) => n === pathways[i])) {
    issues.push("tree rehydration scrambled OR order");
  }

  let unresolved = 0;
  const materialized = readMaterializedPathways(tree, boundaries.length);
  materialized.forEach((pathwayNode, index) => {
    const boundary = boundaries[index];
    if (!boundary) return;
    const { items } = buildPathwayRows(boundary);
    const window =
      boundary.source === "tree"
        ? { start: 0, end: rule.recommendation_text.length }
        : undefined;
    unresolved += countUnresolvedRows(
      items,
      buildRowResolver(pathwayNode, rule.recommendation_text, window),
    );
  });

  const hardBroken = issues.some(
    (i) =>
      i.includes("fake Situation") ||
      i.includes("stacked highlights") ||
      i.includes("without tree fallback") ||
      i.includes("scrambled") ||
      i.includes("painted situation"),
  );

  if (hardBroken) {
    return {
      bucket: "broken_rehydration",
      issues,
      mode: "multi",
      pathwayCount: pathways.length,
      boundarySource: source,
      unresolved,
      leafCount,
    };
  }

  if (unresolved > 0) {
    return {
      bucket: "rehydrates_but_conditions_gap",
      issues: [...issues, `${unresolved} guideline row(s) need a match if opened in Conditions`],
      mode: "multi",
      pathwayCount: pathways.length,
      boundarySource: source,
      unresolved,
      leafCount,
    };
  }

  return {
    bucket: source === "tree" ? "table_tree_ok" : "ready_review",
    issues,
    mode: "multi",
    pathwayCount: pathways.length,
    boundarySource: source,
    unresolved,
    leafCount,
  };
}

function main(): void {
  const fixture = path.join(
    __dirname,
    "../src/app/admin/guidance/EditRuleDialog/__tests__/fixtures/pendingNg12Rehydration.json",
  );
  const rules = JSON.parse(fs.readFileSync(fixture, "utf8")) as PendingRule[];

  const byName = new Map<string, PendingRule[]>();
  for (const r of rules) {
    const key = r.name.replace(/^Rule:\s*/, "").trim();
    const list = byName.get(key) ?? [];
    list.push(r);
    byName.set(key, list);
  }

  const rows = rules.map((rule) => {
    const result = classify(rule);
    return {
      name: rule.name,
      rule_id: rule.rule_id,
      has_action: rule.has_action,
      needs_human_review: rule.needs_human_review,
      duplicate_name_count: byName.get(rule.name.replace(/^Rule:\s*/, "").trim())?.length ?? 1,
      ...result,
    };
  });

  const buckets: Record<string, typeof rows> = {};
  for (const row of rows) {
    (buckets[row.bucket] ??= []).push(row);
  }

  const ready = [
    ...(buckets.ready_review ?? []),
    ...(buckets.ready_single ?? []),
    ...(buckets.table_tree_ok ?? []),
  ];

  console.log(
    JSON.stringify(
      {
        total: rows.length,
        unique_names: byName.size,
        duplicates: [...byName.entries()]
          .filter(([, v]) => v.length > 1)
          .map(([name, v]) => ({ name, count: v.length })),
        counts: Object.fromEntries(
          Object.entries(buckets).map(([k, v]) => [k, v.length]),
        ),
        already_correctly_created: ready.map((r) => ({
          name: r.name,
          mode: r.mode,
          pathways: r.pathwayCount || undefined,
          source: r.boundarySource,
          leaves: r.leafCount,
          has_action: r.has_action,
          duplicates: r.duplicate_name_count > 1 ? r.duplicate_name_count : undefined,
        })),
        conditions_gap: (buckets.rehydrates_but_conditions_gap ?? []).map((r) => ({
          name: r.name,
          pathways: r.pathwayCount,
          source: r.boundarySource,
          unresolved: r.unresolved,
          issues: r.issues,
        })),
        empty_or_non_codable: [
          ...(buckets.empty_or_no_leaves ?? []),
          ...(buckets.non_codable_signal ?? []),
        ].map((r) => ({
          name: r.name,
          bucket: r.bucket,
          issues: r.issues,
          has_action: r.has_action,
        })),
        broken: (buckets.broken_rehydration ?? []).map((r) => ({
          name: r.name,
          issues: r.issues,
        })),
      },
      null,
      2,
    ),
  );
}

main();
