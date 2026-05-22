/**
 * Pure-function tests for tree operations -- VT-LEO-AI-152.
 *
 * Covers replace/add/remove operations, validation rules, and the round-trip
 * between assignNodeIds and stripNodeIds (server payload preserves shape).
 */

import {
  applyUpdate,
  assignNodeIds,
  findValidationError,
  hasOrRootWithPrerequisites,
  isTreeVisuallyEmpty,
  promoteOrPrerequisites,
  stripNodeIds,
  wrapRootInAnd,
} from "../treeOps";
import type { EditableLogicNode } from "../types";

function makeTree(): EditableLogicNode {
  return assignNodeIds({
    kind: "AND",
    children: [
      {
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: 40,
        unit: "years",
      },
      {
        kind: "OR",
        children: [
          {
            kind: "CONCEPT",
            criterion: {
              snomed_concept_id: "49727002",
              preferred_term: "Cough (finding)",
              semantic_tag: "finding",
            },
          },
        ],
      },
    ],
  });
}

describe("treeOps", () => {
  it("replace_concept swaps the criterion on the targeted node", () => {
    const tree = makeTree();
    const conceptNode = tree.children![1].children![0];
    const updated = applyUpdate(tree, {
      kind: "replace_concept",
      nodeId: conceptNode.node_id,
      criterion: {
        snomed_concept_id: "84229001",
        preferred_term: "Fatigue (finding)",
        semantic_tag: "finding",
      },
    });
    expect(updated).not.toBeNull();
    const newConcept = updated!.children![1].children![0];
    expect(newConcept.criterion?.snomed_concept_id).toBe("84229001");
    expect(newConcept.criterion?.preferred_term).toBe("Fatigue (finding)");
  });

  it("add_concept inserts a new CONCEPT child under the targeted group", () => {
    const tree = makeTree();
    const orGroup = tree.children![1];
    const updated = applyUpdate(tree, {
      kind: "add_concept",
      parentNodeId: orGroup.node_id,
      criterion: {
        snomed_concept_id: "267036007",
        preferred_term: "Dyspnea (finding)",
        semantic_tag: "finding",
      },
    });
    expect(updated!.children![1].children).toHaveLength(2);
    expect(updated!.children![1].children![1].criterion?.snomed_concept_id).toBe(
      "267036007"
    );
  });

  it("remove deletes the targeted node and refuses to remove the root", () => {
    const tree = makeTree();
    const ageNode = tree.children![0];
    const after = applyUpdate(tree, { kind: "remove", nodeId: ageNode.node_id });
    expect(after!.children).toHaveLength(1);
    expect(after!.children![0].kind).toBe("OR");

    const removeRoot = applyUpdate(tree, { kind: "remove", nodeId: tree.node_id });
    expect(removeRoot).toBeNull();
  });

  it("set_min clamps AT_LEAST minimum to >= 1", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 2,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "B" } },
      ],
    });
    const updated = applyUpdate(tree, { kind: "set_min", nodeId: tree.node_id, min: 0 });
    expect(updated!.min).toBe(1);
  });

  it("findValidationError flags an empty group in plain English", () => {
    const tree = assignNodeIds({ kind: "AND", children: [] });
    const msg = findValidationError(tree);
    expect(msg).toMatch(/empty/i);
    expect(msg).toMatch(/symptom or patient detail/i);
  });

  it("findValidationError flags AT_LEAST whose min exceeds children", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 5,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
      ],
    });
    const msg = findValidationError(tree);
    expect(msg).toMatch(/asking for more symptoms/i);
  });

  it("findValidationError nudges the user to pick a symptom for an empty pill", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [{ kind: "CONCEPT", criterion: { snomed_concept_id: "", preferred_term: "?" } }],
    });
    const msg = findValidationError(tree);
    expect(msg).toMatch(/pick a symptom or sign/i);
    expect(msg).toMatch(/search box on the right/i);
  });

  it("findValidationError messages do not use technical jargon (health-literacy gate)", () => {
    const trees = [
      assignNodeIds({ kind: "AND", children: [] }),
      assignNodeIds({
        kind: "AND",
        children: [
          { kind: "CONCEPT", criterion: { snomed_concept_id: "", preferred_term: "?" } },
        ],
      }),
      assignNodeIds({
        kind: "AT_LEAST",
        min: 0,
        children: [
          { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
        ],
      }),
    ];
    const messages = trees.map((t) => findValidationError(t) ?? "").join(" | ");
    // Words a reader with reading age 9-11 should not have to parse.
    expect(messages).not.toMatch(/SNOMED/i);
    // Reject the technical token AT_LEAST, but allow the plain-English
    // phrase "at least N".
    expect(messages).not.toMatch(/AT_LEAST/);
    expect(messages).not.toMatch(/\bDEMOGRAPHIC\b/);
    expect(messages).not.toMatch(/\bAND\b/);
    expect(messages).not.toMatch(/\bcriterion\b/i);
  });

  it("findValidationError returns null for a well-formed tree", () => {
    expect(findValidationError(makeTree())).toBeNull();
  });

  it("assignNodeIds normalises lowercase 'concept'/'demographic' kinds", () => {
    // The persisted LLM logic_tree uses lowercase leaf kinds.  Without
    // normalisation the editor used to mis-render those leaves as empty group
    // nodes and surface a spurious "'concept' group cannot be empty" error.
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "demographic" as unknown as "DEMOGRAPHIC",
          field: "age",
          operator: ">=",
          value: 40,
          unit: "years",
        },
        {
          kind: "concept" as unknown as "CONCEPT",
          criterion: {
            snomed_concept_id: "49727002",
            preferred_term: "Cough (finding)",
          },
        },
      ],
    });
    expect(tree.kind).toBe("AND");
    expect(tree.children![0].kind).toBe("DEMOGRAPHIC");
    expect(tree.children![1].kind).toBe("CONCEPT");
    expect(findValidationError(tree)).toBeNull();
  });

  it("stripNodeIds removes node_id while preserving structure", () => {
    const tree = makeTree();
    const stripped = stripNodeIds(tree);
    expect("node_id" in stripped).toBe(false);
    const orGroup = (stripped.children as Array<Record<string, unknown>>)[1];
    expect("node_id" in orGroup).toBe(false);
    const concept = (orGroup.children as Array<Record<string, unknown>>)[0];
    expect((concept.criterion as Record<string, unknown>).snomed_concept_id).toBe(
      "49727002"
    );
  });

  // ---------------------------------------------------------------------
  // Criterion / seed sanitisation (regression for the 422 bug where the
  // BE LogicCriterion model rejected LLM-provenance fields the FE was
  // forwarding wholesale -- save returned 422, nothing persisted).
  // ---------------------------------------------------------------------

  it("stripNodeIds drops LLM provenance fields from the criterion", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: {
            // Allowed BE fields
            snomed_concept_id: "77176002",
            preferred_term: "Smoker",
            semantic_tag: "finding",
            term: "smoker",
            seeds: [
              {
                snomed_concept_id: "77176002",
                preferred_term: "Smoker",
                include_descendants: true,
              },
            ],
            primary_concept_id: "77176002",
            excluded_concept_ids: [],
            // Forbidden LLM-provenance fields written by the rule
            // extraction pipeline (see _apply_leaf_decisions in
            // libs/pipeline_graph/subgraphs/guidance_rule_extraction_v2_impl.py).
            // The BE LogicCriterion has model_config={"extra":"forbid"},
            // so any of these reaching the API triggers a 422.
            node_id: "leaf_1",
            source_text: "current smoker",
            original_phrase: "smoker",
            expansion_source: "llm",
            expanded_from: ["smoker"],
            candidates: [{ concept_id: "1", score: 0.9 }],
            verification_status: "verified",
            verification_reason: "exact match",
            confidence: 0.97,
            resolver_turns: 1,
            needs_human_review: false,
            search_history: [{ q: "smoker" }],
          } as unknown as import("../types").LogicCriterion,
        },
      ],
    });

    const stripped = stripNodeIds(tree);
    const concept = (stripped.children as Array<Record<string, unknown>>)[0];
    const crit = concept.criterion as Record<string, unknown>;

    // Allowed keys survive.
    expect(crit.snomed_concept_id).toBe("77176002");
    expect(crit.preferred_term).toBe("Smoker");
    expect(crit.term).toBe("smoker");
    expect(crit.primary_concept_id).toBe("77176002");
    expect(Array.isArray(crit.seeds)).toBe(true);

    // Forbidden keys are stripped before POST.
    for (const k of [
      "node_id",
      "source_text",
      "original_phrase",
      "expansion_source",
      "expanded_from",
      "candidates",
      "verification_status",
      "verification_reason",
      "confidence",
      "resolver_turns",
      "needs_human_review",
      "search_history",
    ]) {
      expect(k in crit).toBe(false);
    }
  });

  it("stripNodeIds whitelists per-seed keys too (BE LogicSeed extra=forbid)", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "77176002",
            preferred_term: "Smoker",
            seeds: [
              {
                snomed_concept_id: "266919005",
                preferred_term: "Cigarette smoker",
                semantic_tag: "finding",
                include_descendants: true,
                distance_child: 2,
                // Forbidden -- a stale node_id rode in via the loaded tree.
                node_id: "seed_42",
                candidates: [{ concept_id: "x" }],
              },
            ],
            primary_concept_id: "266919005",
          } as unknown as import("../types").LogicCriterion,
        },
      ],
    });

    const stripped = stripNodeIds(tree);
    const concept = (stripped.children as Array<Record<string, unknown>>)[0];
    const seed = ((concept.criterion as Record<string, unknown>).seeds as Array<
      Record<string, unknown>
    >)[0];

    expect(seed.snomed_concept_id).toBe("266919005");
    expect(seed.preferred_term).toBe("Cigarette smoker");
    expect(seed.include_descendants).toBe(true);
    expect(seed.distance_child).toBe(2);
    expect("node_id" in seed).toBe(false);
    expect("candidates" in seed).toBe(false);
  });

  it("isTreeVisuallyEmpty treats a leaf at the root as non-empty", () => {
    const leaf = assignNodeIds({
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "49727002",
        preferred_term: "Cough (finding)",
      },
    });
    expect(isTreeVisuallyEmpty(leaf)).toBe(false);
    expect(isTreeVisuallyEmpty(assignNodeIds({ kind: "AND", children: [] }))).toBe(
      true,
    );
  });

  it("wrapRootInAnd wraps a leaf root so add_concept can attach siblings", () => {
    const leaf = assignNodeIds({
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "49727002",
        preferred_term: "Cough (finding)",
      },
    });
    const wrapped = wrapRootInAnd(leaf);
    expect(wrapped.kind).toBe("AND");
    expect(wrapped.children).toHaveLength(1);
    const withSibling = applyUpdate(wrapped, {
      kind: "add_concept",
      parentNodeId: wrapped.node_id,
      criterion: {
        snomed_concept_id: "84229001",
        preferred_term: "Fatigue (finding)",
      },
    });
    expect(withSibling?.children).toHaveLength(2);
  });
});

describe("promoteOrPrerequisites", () => {
  function makeOrWithAge(): EditableLogicNode {
    return assignNodeIds({
      kind: "OR",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 50, unit: "years" },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "FIT" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Blood" } },
      ],
    });
  }

  it("promotes demographic to AND prerequisite, wraps remaining concepts in OR", () => {
    const tree = makeOrWithAge();
    const fixed = promoteOrPrerequisites(tree);
    expect(fixed.kind).toBe("AND");
    const kids = fixed.children ?? [];
    expect(kids.some((c) => c.kind === "DEMOGRAPHIC")).toBe(true);
    const orGroup = kids.find((c) => c.kind === "OR");
    expect(orGroup).toBeDefined();
    expect(orGroup?.children).toHaveLength(2);
  });

  it("wraps a single remaining concept in OR so pathways stay editable", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 18, unit: "years" },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Mycoplasma" } },
      ],
    });
    const fixed = promoteOrPrerequisites(tree);
    expect(fixed.kind).toBe("AND");
    const kids = fixed.children ?? [];
    expect(kids.some((c) => c.kind === "DEMOGRAPHIC")).toBe(true);
    const orGroup = kids.find((c) => c.kind === "OR");
    expect(orGroup).toBeDefined();
    expect(orGroup?.children).toHaveLength(1);
    expect(orGroup?.children?.[0].kind).toBe("CONCEPT");
  });

  it("produces AND with only prerequisites when there are no other children", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 18, unit: "years" },
      ],
    });
    const fixed = promoteOrPrerequisites(tree);
    expect(fixed.kind).toBe("AND");
    const kids = fixed.children ?? [];
    expect(kids).toHaveLength(1);
    expect(kids[0].kind).toBe("DEMOGRAPHIC");
  });

  it("returns unchanged tree when OR has no prerequisites", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "FIT" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Blood" } },
      ],
    });
    expect(promoteOrPrerequisites(tree)).toBe(tree);
  });

  it("returns unchanged tree when root is not OR", () => {
    const tree = assignNodeIds({ kind: "AND", children: [] });
    expect(promoteOrPrerequisites(tree)).toBe(tree);
  });
});

describe("hasOrRootWithPrerequisites", () => {
  it("detects OR root with demographic child", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 50, unit: "years" },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "FIT" } },
      ],
    });
    expect(hasOrRootWithPrerequisites(tree)).toBe(true);
  });

  it("returns false for AND root", () => {
    const tree = assignNodeIds({ kind: "AND", children: [] });
    expect(hasOrRootWithPrerequisites(tree)).toBe(false);
  });

  it("returns false for OR root with only concepts", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "FIT" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Blood" } },
      ],
    });
    expect(hasOrRootWithPrerequisites(tree)).toBe(false);
  });

  it("returns false for null", () => {
    expect(hasOrRootWithPrerequisites(null)).toBe(false);
  });
});
