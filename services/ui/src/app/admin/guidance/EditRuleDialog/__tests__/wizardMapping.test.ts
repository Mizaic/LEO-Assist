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
  findClusterSubgroupByRole,
  isClusterChildRow,
  isLeadClusterChildRow,
  leafDisplayTerm,
  materializePathways,
  orderPathwayNodesByBoundary,
  pathwayGroupingKey,
  pathwayLetterAt,
  pathwaySummaryText,
  pathwayTextWindow,
  readMaterializedPathways,
  rebuildPathwayOr,
  splitWouldDiscardPathwayLeaves,
  withReifiedPathwayClusters,
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

  // Regression: two pathways sharing identical wording (e.g. NG12
  // 1.2.9's pathway C and pathway D both list "nausea"). Without a
  // textWindow, findBestTextMatch's exactMatch always returns the
  // FIRST occurrence in the whole document -- so a leaf that truly
  // belongs to the SECOND pathway's own text would incorrectly
  // resolve to the first pathway's earlier occurrence, leaving the
  // second pathway's own row permanently unresolved even after the
  // reviewer picked a concept for it.
  it("scopes the match to textWindow so a later pathway's leaf does not resolve to an earlier pathway's identical wording", () => {
    const DUP_TEXT =
      "raised platelet count with nausea, or vomiting with nausea and reflux.";
    const firstNausea = DUP_TEXT.indexOf("nausea");
    const secondNausea = DUP_TEXT.indexOf("nausea", firstNausea + 1);
    expect(secondNausea).toBeGreaterThan(firstNausea);

    const nauseaLeaf: EditableLogicNode = {
      node_id: "nausea-d",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "n1", preferred_term: "Nausea" },
    };
    const pathwayD = pathwayNode([nauseaLeaf]);
    // Pathway D's own text window starts right after pathway C ends
    // (at the ", or " boundary), so it only spans the SECOND
    // occurrence of "nausea".
    const pathwayDWindow = { start: secondNausea - "vomiting with ".length, end: DUP_TEXT.length };

    const unscoped = buildRowResolver(pathwayD, DUP_TEXT);
    const rowAtSecondOccurrence: RecommendationStructureItem = {
      text: "nausea",
      start: secondNausea,
      end: secondNausea + "nausea".length,
    };
    // Without windowing, the resolver anchors "Nausea" onto the FIRST
    // occurrence (pathway C's), so pathway D's own row does not
    // overlap it and stays unresolved -- this is the bug.
    expect(unscoped(rowAtSecondOccurrence)).toBeUndefined();

    const windowed = buildRowResolver(pathwayD, DUP_TEXT, pathwayDWindow);
    expect(windowed(rowAtSecondOccurrence)?.nodeId).toBe("nausea-d");
  });

  // Regression: "I select a code and nothing happens." A reviewer
  // picking a SNOMED code for a row very often picks a term that
  // shares no wording at all with the guideline's own text (e.g.
  // "Indigestion" for a row that reads "treatment-resistant
  // dyspepsia") -- fuzzy text matching alone can never anchor that
  // leaf back onto its row, so the row looked permanently unresolved
  // even though the leaf really was added. source_row_text is an
  // exact-string escape hatch around that.
  it("resolves a row via source_row_text even when the picked term shares no wording with the row", () => {
    const leaf: EditableLogicNode = {
      node_id: "indigestion",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "162031009", preferred_term: "Indigestion" },
      source_row_text: "treatment-resistant dyspepsia",
    };
    const pw = pathwayNode([leaf]);
    const resolver = buildRowResolver(pw, "Consider endoscopy for treatment-resistant dyspepsia.");
    const row: RecommendationStructureItem = {
      text: "treatment-resistant dyspepsia",
      start: 20,
      end: 50,
    };
    const resolution = resolver(row);
    expect(resolution?.nodeId).toBe("indigestion");
    expect(resolution?.preferredTerm?.toLowerCase()).toContain("indigestion");
  });

  it("falls back to fuzzy text matching for leaves with no source_row_text (AI-drafted or Advanced-editor leaves)", () => {
    const pw = pathwayNode([weightLossLeaf()]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("weight loss");
    const row: RecommendationStructureItem = {
      text: "weight loss",
      start,
      end: start + "weight loss".length,
    };
    expect(resolver(row)?.nodeId).toBe("wl");
  });

  it("does not auto-resolve a row from a short preferred-term substring (weak fuzzy match)", () => {
    const shortLeaf: EditableLogicNode = {
      node_id: "weight-only",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "9", preferred_term: "Weight" },
    };
    const pw = pathwayNode([shortLeaf]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("weight loss");
    const row: RecommendationStructureItem = {
      text: "weight loss",
      start,
      end: start + "weight loss".length,
    };
    expect(resolver(row)).toBeUndefined();
  });

  it("prefers an exact source_row_text match over a coincidental fuzzy match elsewhere in the same pathway", () => {
    const fuzzyDecoy = weightLossLeaf(); // "wl", no source_row_text
    const provenanced: EditableLogicNode = {
      node_id: "provenanced",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "2", preferred_term: "Something unrelated" },
      source_row_text: "weight loss",
    };
    const pw = pathwayNode([fuzzyDecoy, provenanced]);
    const resolver = buildRowResolver(pw, TEXT);
    const start = TEXT.toLowerCase().indexOf("weight loss");
    const row: RecommendationStructureItem = {
      text: "weight loss",
      start,
      end: start + "weight loss".length,
    };
    expect(resolver(row)?.nodeId).toBe("provenanced");
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

describe("orderPathwayNodesByBoundary", () => {
  // Regression: NG12 1.2.9 in production, reported directly against
  // the running wizard -- Situation B's "Already confirmed" summary
  // showed situation C's whole 6-item cluster mislabelled as
  // situation A. `readMaterializedPathways` just returns the OR's
  // children in raw array order and every caller had assumed that
  // order already matches the boundaries' own text order. Nothing
  // enforces that: an AI-drafted tree's OR children come from the
  // extraction pipeline, built independently of this wizard's own
  // boundary detector, so container 0 in the tree is not guaranteed
  // to be situation A's container.
  const TEXT_A = "treatment-resistant dyspepsia, or ";
  const TEXT_B = "raised platelet count with nausea and vomiting.";
  const FULL_TEXT = TEXT_A + TEXT_B;
  const boundaryA: PathwayTextBoundary = {
    text: TEXT_A,
    start: 0,
    end: TEXT_A.length,
    source: "heuristic",
  };
  const boundaryB: PathwayTextBoundary = {
    text: TEXT_B,
    start: TEXT_A.length,
    end: FULL_TEXT.length,
    source: "heuristic",
  };

  function dyspepsiaLeaf(): EditableLogicNode {
    return {
      node_id: "dys",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "d1", preferred_term: "Dyspepsia" },
    };
  }
  function plateletLeaf(): EditableLogicNode {
    return {
      node_id: "plt",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "p1", preferred_term: "Raised platelet count" },
    };
  }

  it("re-anchors containers to the boundary their own leaves' text actually matches, undoing a reversed tree order", () => {
    const containerForA = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-dys" };
    const containerForB = { ...pathwayNode([plateletLeaf()]), node_id: "pw-plt" };

    // The tree's OR put B's container first -- exactly the mismatch
    // reported in production.
    const ordered = orderPathwayNodesByBoundary(
      [containerForB, containerForA],
      [boundaryA, boundaryB],
      FULL_TEXT,
    );

    expect(ordered).toEqual([containerForA, containerForB]);
  });

  it("leaves already-correctly-ordered containers untouched", () => {
    const containerForA = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-dys" };
    const containerForB = { ...pathwayNode([plateletLeaf()]), node_id: "pw-plt" };

    const ordered = orderPathwayNodesByBoundary(
      [containerForA, containerForB],
      [boundaryA, boundaryB],
      FULL_TEXT,
    );

    expect(ordered).toEqual([containerForA, containerForB]);
  });

  it("keeps an empty (no leaves yet) container in its remaining relative slot -- it carries no content evidence either way", () => {
    const containerForA = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-dys" };
    const emptyContainer = { ...pathwayNode([]), node_id: "pw-empty" };

    const ordered = orderPathwayNodesByBoundary(
      [containerForA, emptyContainer],
      [boundaryA, boundaryB],
      FULL_TEXT,
    );

    expect(ordered).toEqual([containerForA, emptyContainer]);
  });

  it("returns containers unchanged when there is no recommendation text to match against", () => {
    const containerForB = { ...pathwayNode([plateletLeaf()]), node_id: "pw-plt" };
    const containerForA = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-dys" };

    const ordered = orderPathwayNodesByBoundary(
      [containerForB, containerForA],
      [boundaryA, boundaryB],
      null,
    );

    expect(ordered).toEqual([containerForB, containerForA]);
  });

  it("returns containers unchanged when the counts do not match (nothing sane to reorder)", () => {
    const containerForA = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-dys" };

    const ordered = orderPathwayNodesByBoundary([containerForA], [boundaryA, boundaryB], FULL_TEXT);

    expect(ordered).toEqual([containerForA]);
  });

  it("does not let two containers double-claim the same boundary -- the second falls back to an unclaimed slot", () => {
    // Contrived: both containers' leaves happen to text-match inside
    // boundary A's span. The first container (by original order)
    // keeps the claim; the second is treated as unclaimed so every
    // boundary still gets exactly one container.
    const bothMatchA1 = { ...pathwayNode([dyspepsiaLeaf()]), node_id: "pw-1" };
    const bothMatchA2 = {
      ...pathwayNode([{ ...dyspepsiaLeaf(), node_id: "dys2" }]),
      node_id: "pw-2",
    };

    const ordered = orderPathwayNodesByBoundary(
      [bothMatchA1, bothMatchA2],
      [boundaryA, boundaryB],
      FULL_TEXT,
    );

    expect(ordered).toEqual([bothMatchA1, bothMatchA2]);
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

describe("pathwayTextWindow", () => {
  it("extends each pathway to the next boundary start so nested-list offsets stay owned", () => {
    const boundaries: PathwayTextBoundary[] = [
      { start: 0, end: 10, text: "A lead", source: "structure" },
      { start: 40, end: 50, text: "B lead", source: "structure" },
    ];
    expect(pathwayTextWindow(boundaries, 0, 80)).toEqual({ start: 0, end: 40 });
    expect(pathwayTextWindow(boundaries, 1, 80)).toEqual({ start: 40, end: 80 });
  });

  it("returns undefined for a single-pathway rule (no OR to scope)", () => {
    const boundaries: PathwayTextBoundary[] = [
      { start: 0, end: 20, text: "only", source: "heuristic" },
    ];
    expect(pathwayTextWindow(boundaries, 0, 20)).toBeUndefined();
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

  it("rebuilds the OR to exactly N empty shells when the existing child count is too low", () => {
    const pwA = pathwayNode();
    const pwB = { ...pathwayNode(), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    const updates: NodeUpdate[] = [];
    const result = materializePathways(tree, 4, (u) => updates.push(u));
    expect(result).toEqual([]);
    expect(updates).toHaveLength(1);
    expect(updates[0].kind).toBe("replace_root");
    if (updates[0].kind !== "replace_root") return;
    expect(updates[0].node.kind).toBe("OR");
    expect(updates[0].node.children).toHaveLength(4);
    expect(updates[0].node.children!.every((c) => (c.children ?? []).length === 0)).toBe(
      true,
    );
  });

  it("rebuilds the OR when an AI draft has MORE pathways than confirmed situations", () => {
    const children = Array.from({ length: 6 }, (_, i) => ({
      ...pathwayNode([{ ...weightLossLeaf(), node_id: `leaf-${i}` }]),
      node_id: `pw-${i}`,
      pathway_key: `pk_${i}`,
    }));
    const age = ageLeaf();
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [age, { node_id: "or", kind: "OR", children }],
    };
    const updates: NodeUpdate[] = [];
    expect(materializePathways(tree, 4, (u) => updates.push(u))).toEqual([]);
    expect(updates).toHaveLength(1);
    if (updates[0].kind !== "replace_root") return;
    const rebuilt = updates[0].node;
    expect(rebuilt.kind).toBe("AND");
    expect(rebuilt.children![0]).toBe(age);
    const or = rebuilt.children!.find((c) => c.kind === "OR")!;
    expect(or.children).toHaveLength(4);
    expect(or.children!.every((c) => (c.children ?? []).length === 0)).toBe(true);
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

describe("splitWouldDiscardPathwayLeaves", () => {
  it("is false when there is no pathway split yet -- nothing to lose", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    expect(splitWouldDiscardPathwayLeaves(tree, 2)).toBe(false);
  });

  it("is false when the new count matches what's already materialized", () => {
    const pwA = pathwayNode([weightLossLeaf()]);
    const pwB = { ...pathwayNode([ageLeaf()]), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    expect(splitWouldDiscardPathwayLeaves(tree, 2)).toBe(false);
  });

  it("is false when the count differs but every existing pathway is still empty (nothing to lose)", () => {
    const pwA = pathwayNode([]);
    const pwB = { ...pathwayNode([]), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    expect(splitWouldDiscardPathwayLeaves(tree, 3)).toBe(false);
  });

  it("is true when the count differs AND at least one existing pathway already has leaves", () => {
    const pwA = pathwayNode([weightLossLeaf()]);
    const pwB = { ...pathwayNode([]), node_id: "pw-b" };
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pwA, pwB] };
    expect(splitWouldDiscardPathwayLeaves(tree, 3)).toBe(true);
    expect(splitWouldDiscardPathwayLeaves(tree, 1)).toBe(true);
  });
});

describe("rebuildPathwayOr", () => {
  it("preserves prerequisites and mints a fresh 4-child OR", () => {
    const age = ageLeaf();
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [
        age,
        {
          node_id: "or",
          kind: "OR",
          children: Array.from({ length: 6 }, (_, i) => ({
            node_id: `pw-${i}`,
            kind: "AND" as const,
            pathway_key: `old_${i}`,
            children: [],
          })),
        },
      ],
    };
    const next = rebuildPathwayOr(tree, 4);
    expect(next.children![0]).toBe(age);
    expect(next.children!.find((c) => c.kind === "OR")!.children).toHaveLength(4);
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

  it("splits a plain clinical 'X with Y' into two AND rows (NG12 situation B)", () => {
    const boundary: PathwayTextBoundary = {
      text: "upper abdominal pain with low haemoglobin levels",
      start: 100,
      end: 148,
      source: "structure",
    };
    const { items, hasCluster } = buildPathwayRows(boundary);
    expect(hasCluster).toBe(false);
    expect(items.map((i) => i.text)).toEqual([
      "upper abdominal pain",
      "low haemoglobin levels",
    ]);
    expect(items[0].start).toBe(100);
    expect(items[1].start).toBeGreaterThan(items[0].end);
  });

  it("does not split 'with any of the following' via the plain-with path", () => {
    const { items, hasCluster } = buildPathwayRows(CLUSTER_BOUNDARY);
    expect(hasCluster).toBe(true);
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

// NG12 1.2.9 pathway D -- "nausea or vomiting with any of the
// following: weight loss, reflux, dyspepsia, upper abdominal pain."
// Both "nausea" and "vomiting" need the SAME trailing findings; see
// `looksLikeLeadOrCluster`'s doc comment in pathwayTextSplit.ts.
const TWO_CLUSTER_BOUNDARY: PathwayTextBoundary = {
  text:
    "nausea or vomiting with any of the following: weight loss, reflux, " +
    "dyspepsia, upper abdominal pain.",
  start: 0,
  end: 96,
  source: "heuristic",
};

describe("buildPathwayRows: a lead-or cluster plus a trailing cluster", () => {
  it("flattens both clusters' member rows into items, with leadCluster identifying the front two", () => {
    const { items, hasCluster, leadCluster } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    expect(hasCluster).toBe(true);
    expect(leadCluster?.items.map((r) => r.text)).toEqual(["nausea", "vomiting"]);
    expect(items.map((r) => r.text)).toEqual([
      "nausea",
      "vomiting",
      "weight loss",
      "reflux",
      "dyspepsia",
      "upper abdominal pain",
    ]);
  });

  it("gives every row a distinct, non-colliding offset", () => {
    const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    const starts = items.map((r) => r.start);
    expect(new Set(starts).size).toBe(starts.length);
  });

  it("omits leadCluster entirely for the ordinary single-cluster case", () => {
    const { leadCluster } = buildPathwayRows(CLUSTER_BOUNDARY);
    expect(leadCluster).toBeUndefined();
  });
});

describe("isLeadClusterChildRow", () => {
  it("is true for a lead-or cluster's own member row", () => {
    const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    expect(isLeadClusterChildRow(TWO_CLUSTER_BOUNDARY, items[0])).toBe(true);
    expect(isLeadClusterChildRow(TWO_CLUSTER_BOUNDARY, items[1])).toBe(true);
  });

  it("is false for the trailing cluster's own member rows", () => {
    const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    expect(isLeadClusterChildRow(TWO_CLUSTER_BOUNDARY, items[2])).toBe(false);
  });

  it("is false when there is no lead-or cluster at all", () => {
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    expect(isLeadClusterChildRow(CLUSTER_BOUNDARY, items[0])).toBe(false);
  });
});

describe("isClusterChildRow: distinguishes the trailing cluster from a lead-or cluster", () => {
  it("does not treat a lead-or cluster's own member row as a trailing-cluster child", () => {
    const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    expect(isClusterChildRow(TWO_CLUSTER_BOUNDARY, items[0])).toBe(false);
  });

  it("still treats the trailing cluster's own member rows as trailing-cluster children", () => {
    const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
    expect(isClusterChildRow(TWO_CLUSTER_BOUNDARY, items[2])).toBe(true);
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

describe("pathwayGroupingKey", () => {
  it("uses the pathway's own stable pathway_key when it has one", () => {
    const node = { ...pathwayNode([weightLossLeaf()]), pathway_key: "pw_c" };
    expect(pathwayGroupingKey(node, 0)).toBe("pw_c");
    // The same pathway keeps the same grouping key even if a
    // merge/split in Step 2 moves it to a different array index --
    // that is the entire point of keying by pathway_key.
    expect(pathwayGroupingKey(node, 5)).toBe("pw_c");
  });

  it("falls back to a positional key only when there is no pathway_key at all", () => {
    const node = pathwayNode([weightLossLeaf()]);
    delete (node as { pathway_key?: string }).pathway_key;
    expect(pathwayGroupingKey(node, 2)).toBe("pathway-index-2");
    expect(pathwayGroupingKey(null, 3)).toBe("pathway-index-3");
    expect(pathwayGroupingKey(undefined, 4)).toBe("pathway-index-4");
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
      role: "trailing",
    });
  });

  it("routes a cluster child straight to the pathway when grouping is AND", () => {
    const pw = pathwayNode([]);
    const { items } = buildPathwayRows(CLUSTER_BOUNDARY);
    const child = items[0].children![0];
    const decision = decideRowClickTarget(pw, CLUSTER_BOUNDARY, child, undefined, "AND");
    expect(decision).toEqual({ action: "add", parentNodeId: "pw-a", text: child.text });
  });

  describe("with two clusters in the same pathway", () => {
    it("routes a lead-cluster member row to the 'lead' subgroup when one already exists", () => {
      const leadSubgroup: EditableLogicNode = {
        node_id: "cluster-lead",
        kind: "AT_LEAST",
        min: 1,
        cluster_role: "lead",
        children: [],
      };
      const pw = pathwayNode([leadSubgroup]);
      const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
      const decision = decideRowClickTarget(
        pw,
        TWO_CLUSTER_BOUNDARY,
        items[0],
        undefined,
        undefined,
        "AT_LEAST",
      );
      expect(decision).toEqual({ action: "add", parentNodeId: "cluster-lead", text: "nausea" });
    });

    it("requests a fresh 'lead' subgroup when none exists yet, even if a 'trailing' one does", () => {
      const trailingSubgroup: EditableLogicNode = {
        node_id: "cluster-trailing",
        kind: "AT_LEAST",
        min: 1,
        children: [],
      };
      const pw = pathwayNode([trailingSubgroup]);
      const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
      const decision = decideRowClickTarget(
        pw,
        TWO_CLUSTER_BOUNDARY,
        items[0],
        undefined,
        undefined,
        "AT_LEAST",
      );
      expect(decision).toEqual({
        action: "create_subgroup_then_add",
        pathwayNodeId: "pw-a",
        text: "nausea",
        role: "lead",
      });
    });

    it("routes a trailing-cluster member row to the untagged (trailing) subgroup, not the lead one", () => {
      const leadSubgroup: EditableLogicNode = {
        node_id: "cluster-lead",
        kind: "AT_LEAST",
        min: 1,
        cluster_role: "lead",
        children: [],
      };
      const trailingSubgroup: EditableLogicNode = {
        node_id: "cluster-trailing",
        kind: "AT_LEAST",
        min: 1,
        children: [],
      };
      const pw = pathwayNode([leadSubgroup, trailingSubgroup]);
      const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
      const trailingRow = items[2];
      const decision = decideRowClickTarget(
        pw,
        TWO_CLUSTER_BOUNDARY,
        trailingRow,
        undefined,
        "AT_LEAST",
        "AT_LEAST",
      );
      expect(decision).toEqual({
        action: "add",
        parentNodeId: "cluster-trailing",
        text: "weight loss",
      });
    });

    it("defaults an undecided lead grouping to AT_LEAST (Recommended) so nausea/vomiting are not flat AND", () => {
      const pw = pathwayNode([]);
      const { items } = buildPathwayRows(TWO_CLUSTER_BOUNDARY);
      const decision = decideRowClickTarget(
        pw,
        TWO_CLUSTER_BOUNDARY,
        items[0],
        undefined,
        undefined,
        undefined,
      );
      expect(decision).toEqual({
        action: "create_subgroup_then_add",
        pathwayNodeId: "pw-a",
        text: "nausea",
        role: "lead",
      });
    });
  });
});

describe("withReifiedPathwayClusters", () => {
  it("keeps a pathway DEMOGRAPHIC sibling when reifying AT_LEAST clusters", () => {
    const sex: EditableLogicNode = {
      node_id: "sex",
      kind: "DEMOGRAPHIC",
      field: "sex",
      operator: "=",
      value: "female",
      unit: null,
    };
    const nausea: EditableLogicNode = {
      node_id: "n",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
      source_row_text: "nausea",
    };
    const vomiting: EditableLogicNode = {
      node_id: "v",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" },
      source_row_text: "vomiting",
    };
    const weight: EditableLogicNode = {
      node_id: "w",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "3", preferred_term: "Weight decreased" },
      source_row_text: "weight loss",
    };
    const reflux: EditableLogicNode = {
      node_id: "r",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "4", preferred_term: "Acid reflux" },
      source_row_text: "reflux",
    };
    const pw = pathwayNode([sex, nausea, vomiting, weight, reflux]);
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "OR",
      children: [pw],
    };
    const next = withReifiedPathwayClusters(
      tree,
      "pw-a",
      TWO_CLUSTER_BOUNDARY,
      "AT_LEAST",
      "AT_LEAST",
    );
    const rebuilt = next.children![0];
    const sexLeaf = rebuilt.children!.find((c) => c.kind === "DEMOGRAPHIC");
    expect(sexLeaf?.field).toBe("sex");
    expect(sexLeaf?.value).toBe("female");
    expect(rebuilt.children!.some((c) => c.cluster_role === "lead")).toBe(true);
  });

  it("moves flat AND nausea/vomiting into a lead AT_LEAST and trailing symptoms into another", () => {
    const nausea: EditableLogicNode = {
      node_id: "n",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
      source_row_text: "nausea",
    };
    const vomiting: EditableLogicNode = {
      node_id: "v",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" },
      source_row_text: "vomiting",
    };
    const weight: EditableLogicNode = {
      node_id: "w",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "3", preferred_term: "Weight decreased" },
      source_row_text: "weight loss",
    };
    const reflux: EditableLogicNode = {
      node_id: "r",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "4", preferred_term: "Acid reflux" },
      source_row_text: "reflux",
    };
    const pw = pathwayNode([nausea, vomiting, weight, reflux]);
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "OR",
      children: [pw],
    };
    const next = withReifiedPathwayClusters(
      tree,
      "pw-a",
      TWO_CLUSTER_BOUNDARY,
      "AT_LEAST",
      "AT_LEAST",
    );
    const rebuilt = next.children![0];
    expect(rebuilt.children).toHaveLength(2);
    const lead = rebuilt.children!.find((c) => c.cluster_role === "lead")!;
    const trailing = rebuilt.children!.find((c) => (c.cluster_role ?? "trailing") === "trailing")!;
    expect(lead.kind).toBe("AT_LEAST");
    expect(lead.children!.map((c) => c.source_row_text)).toEqual(["nausea", "vomiting"]);
    expect(trailing.kind).toBe("AT_LEAST");
    expect(trailing.children!.map((c) => c.source_row_text)).toEqual([
      "weight loss",
      "reflux",
    ]);
  });

  // Situation C: platelet AND AT_LEAST(1) of the symptom list -- not a
  // flat ALL of platelet + every symptom (the Review bug in the shot).
  it("keeps the lead finding as AND and wraps trailing symptoms in AT_LEAST (Situation C)", () => {
    const boundary: PathwayTextBoundary = {
      text: "a raised platelet count with any of the following: nausea, vomiting, weight loss, reflux, dyspepsia, upper abdominal pain",
      start: 0,
      end: 120,
      source: "heuristic",
    };
    const platelet: EditableLogicNode = {
      node_id: "plt",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "1",
        preferred_term: "Platelet count above reference range",
      },
      // No source_row_text -- matches the live SNOMED-vs-guideline drift
      // that used to leave Confirm reify as a flat ALL list.
    };
    const symptoms: EditableLogicNode[] = [
      {
        node_id: "n",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "2", preferred_term: "Nausea" },
      },
      {
        node_id: "v",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "3", preferred_term: "Vomiting" },
      },
      {
        node_id: "w",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "4", preferred_term: "Weight decreased" },
      },
      {
        node_id: "r",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "5", preferred_term: "Acid reflux" },
      },
      {
        node_id: "d",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "6", preferred_term: "Indigestion" },
        source_row_text: "dyspepsia",
      },
      {
        node_id: "p",
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "7", preferred_term: "Upper abdominal pain" },
      },
    ];
    const pw = pathwayNode([platelet, ...symptoms]);
    const tree: EditableLogicNode = { node_id: "root", kind: "OR", children: [pw] };
    const next = withReifiedPathwayClusters(
      tree,
      "pw-a",
      boundary,
      "AT_LEAST",
      undefined,
      boundary.text,
    );
    const rebuilt = next.children![0];
    expect(rebuilt.children).toHaveLength(2);
    expect(rebuilt.children![0].node_id).toBe("plt");
    const cluster = rebuilt.children![1];
    expect(cluster.kind).toBe("AT_LEAST");
    expect(cluster.min).toBe(1);
    expect(cluster.children).toHaveLength(6);
  });
});

describe("findClusterSubgroupByRole", () => {
  it("finds the tagged 'lead' subgroup, ignoring an untagged one", () => {
    const lead: EditableLogicNode = { node_id: "l", kind: "AT_LEAST", min: 1, cluster_role: "lead" };
    const trailing: EditableLogicNode = { node_id: "t", kind: "AT_LEAST", min: 1 };
    const pw = pathwayNode([lead, trailing]);
    expect(findClusterSubgroupByRole(pw, "lead")).toBe(lead);
  });

  it("treats an untagged AT_LEAST child as 'trailing' (legacy single-cluster data)", () => {
    const untagged: EditableLogicNode = { node_id: "t", kind: "AT_LEAST", min: 1 };
    const pw = pathwayNode([untagged]);
    expect(findClusterSubgroupByRole(pw, "trailing")).toBe(untagged);
    expect(findClusterSubgroupByRole(pw, "lead")).toBeNull();
  });

  it("returns null when no AT_LEAST child exists at all", () => {
    expect(findClusterSubgroupByRole(pathwayNode([ageLeaf()]), "lead")).toBeNull();
  });
});
