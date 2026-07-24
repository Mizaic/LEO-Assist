/**
 * Unit tests for wizardMapping -- the pure glue between the
 * highlight-to-build wizard's ephemeral boundary/row state and the
 * real EditableLogicNode tree. Covers row resolution (does a row
 * already have a matching leaf?), pathway materialization (never
 * destructive, only ever appends), and the cluster-subgroup lookup.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import {
  buildConfirmedSummaries,
  buildPathwayRows,
  buildRootWithFreshPathways,
  buildRowResolver,
  countUnresolvedRows,
  decideRowClickTarget,
  findClusterSubgroup,
  isClusterChildRow,
  leafDisplayTerm,
  materializePathways,
  pathwayLetterAt,
  pathwaySummaryText,
  readMaterializedPathways,
} from "../HighlightWizard/wizardMapping";
import type { EditableLogicNode, NodeUpdate } from "../types";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";

const TEXT = "In people aged 55 or over with weight loss and nausea.";

function ageLeaf(): EditableLogicNode {
  return { node_id: "age", kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "55" };
}

function weightLossLeaf(): EditableLogicNode {
  return {
    node_id: "wl",
    kind: "CONCEPT",
    criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
  };
}

function pathwayNode(children: EditableLogicNode[] = []): EditableLogicNode {
  return { node_id: "pw-a", kind: "AND", pathway_key: "pw_1", children };
}

describe("leafDisplayTerm / pathwaySummaryText", () => {
  it("renders a DEMOGRAPHIC leaf's own value", () => {
    expect(leafDisplayTerm(ageLeaf())).toContain("55");
  });

  it("renders a CONCEPT leaf's preferred term", () => {
    expect(leafDisplayTerm(weightLossLeaf()).toLowerCase()).toContain("weight loss");
  });

  it("joins a pathway's own leaves with commas", () => {
    const pw = pathwayNode([ageLeaf(), weightLossLeaf()]);
    expect(pathwaySummaryText(pw)).toContain("weight loss");
  });

  it("falls back to a placeholder for an empty pathway", () => {
    expect(pathwaySummaryText(pathwayNode([]))).toBe("(no conditions yet)");
  });
});

describe("buildRowResolver", () => {
  it("resolves a row whose span overlaps an existing leaf's own match", () => {
    const pw = pathwayNode([weightLossLeaf()]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("weight loss");
    const row: RecommendationStructureItem = {
      text: "weight loss",
      start,
      end: start + "weight loss".length,
    };
    const resolution = resolver(row);
    expect(resolution?.nodeId).toBe("wl");
    expect(resolution?.preferredTerm?.toLowerCase()).toContain("weight loss");
  });

  it("leaves a row with no matching leaf unresolved", () => {
    const pw = pathwayNode([weightLossLeaf()]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("nausea");
    const row: RecommendationStructureItem = {
      text: "nausea",
      start,
      end: start + "nausea".length,
    };
    expect(resolver(row)).toBeUndefined();
  });

  it("finds leaves nested inside a cluster subgroup, not just direct children", () => {
    const cluster: EditableLogicNode = { node_id: "cluster", kind: "AT_LEAST", min: 1, children: [weightLossLeaf()] };
    const pw = pathwayNode([cluster]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("weight loss");
    const row: RecommendationStructureItem = {
      text: "weight loss",
      start,
      end: start + "weight loss".length,
    };
    expect(resolver(row)?.nodeId).toBe("wl");
  });
});

describe("countUnresolvedRows", () => {
  it("counts a flat list of unresolved rows", () => {
    const items: RecommendationStructureItem[] = [
      { text: "a", start: 0, end: 1 },
      { text: "b", start: 1, end: 2 },
    ];
    expect(countUnresolvedRows(items, () => undefined)).toBe(2);
  });

  it("counts nested cluster children too", () => {
    const items: RecommendationStructureItem[] = [
      {
        text: "lead",
        start: 0,
        end: 4,
        children: [
          { text: "a", start: 5, end: 6 },
          { text: "b", start: 6, end: 7 },
        ],
      },
    ];
    expect(countUnresolvedRows(items, () => undefined)).toBe(3);
  });

  it("returns 0 once every row resolves", () => {
    const items: RecommendationStructureItem[] = [{ text: "a", start: 0, end: 1 }];
    expect(
      countUnresolvedRows(items, () => ({ preferredTerm: "matched" })),
    ).toBe(0);
  });
});

describe("readMaterializedPathways", () => {
  it("returns [] when there is no pathway split yet", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    expect(readMaterializedPathways(tree, 3)).toEqual([]);
  });

  it("returns the OR's children when the count already matches", () => {
    const pwA = pathwayNode();
    const pwB = { ...pathwayNode(), node_id: "pw-b" };
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "OR",
      children: [pwA, pwB],
    };
    expect(readMaterializedPathways(tree, 2)).toEqual([pwA, pwB]);
  });

  it("returns [] when the OR has fewer children than boundaries", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pathwayNode()] };
    expect(readMaterializedPathways(tree, 3)).toEqual([]);
  });
});

describe("buildRootWithFreshPathways", () => {
  it("wraps a bare leaf root in a new AND alongside the fresh OR", () => {
    const tree = ageLeaf();
    const built = buildRootWithFreshPathways(tree, 2);
    expect(built.kind).toBe("AND");
    expect(built.children).toHaveLength(2);
    expect(built.children![0]).toBe(tree);
    const or = built.children![1];
    expect(or.kind).toBe("OR");
    expect(or.children).toHaveLength(2);
    or.children!.forEach((pw) => {
      expect(pw.kind).toBe("AND");
      expect(pw.pathway_key).toBeTruthy();
    });
  });

  it("appends the fresh OR to an existing AND root's children, preserving them", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    const built = buildRootWithFreshPathways(tree, 3);
    expect(built.node_id).toBe("root");
    expect(built.children).toHaveLength(2);
    expect(built.children![0]).toBe(tree.children![0]);
    expect(built.children![1].kind).toBe("OR");
    expect(built.children![1].children).toHaveLength(3);
  });

  it("mints a distinct pathway_key for every fresh pathway", () => {
    const built = buildRootWithFreshPathways(ageLeaf(), 3);
    const or = built.children![1];
    const keys = or.children!.map((pw) => pw.pathway_key);
    expect(new Set(keys).size).toBe(3);
  });
});

describe("materializePathways", () => {
  it("emits no updates and returns the existing pathways when the count already matches", () => {
    const pwA = pathwayNode();
    const pwB = { ...pathwayNode(), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    const updates: NodeUpdate[] = [];
    const result = materializePathways(tree, 2, (u) => updates.push(u));
    expect(result).toEqual([pwA, pwB]);
    expect(updates).toHaveLength(0);
  });

  it("appends only the missing groups to an existing OR (2+ children already, so it is a recognized split), never touching existing children", () => {
    const pwA = pathwayNode();
    const pwB = { ...pathwayNode(), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    const updates: NodeUpdate[] = [];
    const result = materializePathways(tree, 4, (u) => updates.push(u));
    expect(result).toEqual([]);
    expect(updates).toEqual([
      { kind: "add_group", parentNodeId: "root", groupKind: "AND" },
      { kind: "add_group", parentNodeId: "root", groupKind: "AND" },
    ]);
  });

  it("emits a single replace_root when there is no pathway split at all", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    const updates: NodeUpdate[] = [];
    const result = materializePathways(tree, 2, (u) => updates.push(u));
    expect(result).toEqual([]);
    expect(updates).toHaveLength(1);
    expect(updates[0].kind).toBe("replace_root");
  });
});

describe("findClusterSubgroup", () => {
  it("finds the AT_LEAST child when one exists", () => {
    const cluster: EditableLogicNode = { node_id: "cluster", kind: "AT_LEAST", min: 1, children: [] };
    const pw = pathwayNode([ageLeaf(), cluster]);
    expect(findClusterSubgroup(pw)).toBe(cluster);
  });

  it("returns null when no AT_LEAST child exists yet", () => {
    expect(findClusterSubgroup(pathwayNode([ageLeaf()]))).toBeNull();
  });
});

const CLUSTER_BOUNDARY: PathwayTextBoundary = {
  text: "indigestion with any of the following: nausea, vomiting or weight loss",
  start: 0,
  end: 72,
  source: "heuristic",
};

const PLAIN_BOUNDARY: PathwayTextBoundary = {
  text: "upper abdominal pain",
  start: 0,
  end: 20,
  source: "structure",
};

describe("buildPathwayRows", () => {
  it("returns a single leaf row with no cluster for a plain boundary", () => {
    const { items, hasCluster } = buildPathwayRows(PLAIN_BOUNDARY);
    expect(hasCluster).toBe(false);
    expect(items).toHaveLength(1);
  });

  it("detects a lead row plus cluster children for a boundary with 'any of the following'", () => {
    const { items, hasCluster } = buildPathwayRows(CLUSTER_BOUNDARY);
    expect(hasCluster).toBe(true);
    expect(items[0].children?.length).toBeGreaterThan(0);
  });
});

describe("isClusterChildRow", () => {
  it("is false for a plain, non-cluster boundary's own row", () => {
    const { items } = buildPathwayRows(PLAIN_BOUNDARY);
    expect(isClusterChildRow(PLAIN_BOUNDARY, items[0])).toBe(false);
  });

  it("is false for the lead row of a cluster boundary", () => {
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    expect(isClusterChildRow(CLUSTER_BOUNDARY, items[0])).toBe(false);
  });

  it("is true for one of the cluster's own nested child rows", () => {
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    const child = items[0].children![0];
    expect(isClusterChildRow(CLUSTER_BOUNDARY, child)).toBe(true);
  });
});

describe("pathwayLetterAt / buildConfirmedSummaries", () => {
  it("labels pathways A, B, C...", () => {
    expect(pathwayLetterAt(0)).toBe("A");
    expect(pathwayLetterAt(1)).toBe("B");
    expect(pathwayLetterAt(25)).toBe("Z");
  });

  it("summarizes only the pathways strictly before uptoIndex", () => {
    const pwA = pathwayNode([weightLossLeaf()]);
    const pwB = { ...pathwayNode([ageLeaf()]), node_id: "pw-b" };
    const summaries = buildConfirmedSummaries([pwA, pwB], 1);
    expect(summaries).toHaveLength(1);
    expect(summaries[0].letter).toBe("A");
    expect(summaries[0].summary.toLowerCase()).toContain("weight loss");
  });
});

describe("decideRowClickTarget", () => {
  const plainRow: RecommendationStructureItem = { text: "upper abdominal pain", start: 0, end: 20 };

  it("routes to select when the row already resolves to a leaf", () => {
    const pw = pathwayNode([weightLossLeaf()]);
    const decision = decideRowClickTarget(pw, PLAIN_BOUNDARY, plainRow, { nodeId: "wl" }, undefined);
    expect(decision).toEqual({ action: "select", nodeId: "wl" });
  });

  it("routes a plain unresolved row to add directly under the pathway", () => {
    const pw = pathwayNode([]);
    const decision = decideRowClickTarget(pw, PLAIN_BOUNDARY, plainRow, undefined, undefined);
    expect(decision).toEqual({ action: "add", parentNodeId: "pw-a", text: plainRow.text });
  });

  it("routes an unresolved cluster child to the existing AT_LEAST subgroup when one exists", () => {
    const subgroup: EditableLogicNode = { node_id: "cluster-1", kind: "AT_LEAST", min: 1, children: [] };
    const pw = pathwayNode([subgroup]);
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    const child = items[0].children![0];
    const decision = decideRowClickTarget(pw, CLUSTER_BOUNDARY, child, undefined, "AT_LEAST");
    expect(decision).toEqual({ action: "add", parentNodeId: "cluster-1", text: child.text });
  });

  it("requests a fresh subgroup before adding when AT_LEAST is chosen but no subgroup exists yet", () => {
    const pw = pathwayNode([]);
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    const child = items[0].children![0];
    const decision = decideRowClickTarget(pw, CLUSTER_BOUNDARY, child, undefined, "AT_LEAST");
    expect(decision).toEqual({
      action: "create_subgroup_then_add",
      pathwayNodeId: "pw-a",
      text: child.text,
    });
  });

  it("routes a cluster child straight to the pathway when grouping is AND", () => {
    const pw = pathwayNode([]);
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    const child = items[0].children![0];
    const decision = decideRowClickTarget(pw, CLUSTER_BOUNDARY, child, undefined, "AND");
    expect(decision).toEqual({ action: "add", parentNodeId: "pw-a", text: child.text });
  });
});
