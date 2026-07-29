/**
 * Pure-function tests for tree operations -- VT-LEO-AI-152.
 *
 * Covers replace/add/remove operations, validation rules, and the round-trip
 * between assignNodeIds and stripNodeIds (server payload preserves shape).
 */

import {
  addPrerequisiteToOrSymptoms,
  applyUpdate,
  assignNodeIds,
  ensurePathwayKeys,
  findAllValidationErrors,
  findValidationError,
  findWizardValidationErrors,
  hasOrRootSymptomsOnly,
  hasOrRootWithPrerequisites,
  isOrGroupSymptomsOnly,
  isTreeVisuallyEmpty,
  mintPathwayKey,
  promoteOrPrerequisites,
  pruneEmptyClusterShells,
  stripNodeIds,
  wrapRootInAnd,
} from "../treeOps";
import { liftSharedPathwayDemographics } from "../liftSharedPathwayDemographics";
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

  // See EditableLogicNode.source_row_text's doc comment: the
  // highlight-to-build wizard tags a leaf it adds with the row's own
  // text, so the row can find its way back to that leaf even when the
  // picked SNOMED term shares no wording with it.
  it("add_concept tags the new leaf with sourceRowText when provided", () => {
    const tree = makeTree();
    const orGroup = tree.children![1];
    const updated = applyUpdate(tree, {
      kind: "add_concept",
      parentNodeId: orGroup.node_id,
      criterion: {
        snomed_concept_id: "162031009",
        preferred_term: "Indigestion",
        semantic_tag: "finding",
      },
      sourceRowText: "treatment-resistant dyspepsia",
    });
    expect(updated!.children![1].children![1].source_row_text).toBe(
      "treatment-resistant dyspepsia",
    );
  });

  it("add_concept leaves source_row_text unset when sourceRowText is omitted", () => {
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
    expect(updated!.children![1].children![1].source_row_text).toBeUndefined();
  });

  it("add_group nests a new empty OR sub-group under an AND pathway, enabling AND + a set of OR's", () => {
    const tree = makeTree();
    const updated = applyUpdate(tree, {
      kind: "add_group",
      parentNodeId: tree.node_id,
      groupKind: "OR",
    });
    expect(updated!.children).toHaveLength(3);
    const newGroup = updated!.children![2];
    expect(newGroup.kind).toBe("OR");
    expect(newGroup.children).toEqual([]);
    // The new sub-group can then take its own CONCEPT children,
    // OR'd together, while sitting alongside the AND siblings.
    const withConcept = applyUpdate(updated!, {
      kind: "add_concept",
      parentNodeId: newGroup.node_id,
      criterion: {
        snomed_concept_id: "84229001",
        preferred_term: "Fatigue (finding)",
        semantic_tag: "finding",
      },
    });
    expect(withConcept!.children![2].children).toHaveLength(1);
    expect(withConcept!.children![2].children![0].criterion?.snomed_concept_id).toBe(
      "84229001",
    );
  });

  it("add_group is a no-op when the target cannot have children", () => {
    const tree = makeTree();
    const conceptNode = tree.children![1].children![0];
    const updated = applyUpdate(tree, {
      kind: "add_group",
      parentNodeId: conceptNode.node_id,
      groupKind: "AND",
    });
    expect(updated).toEqual(tree);
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
    expect(msg).toMatch(/symptom, procedure, situation, or patient detail/i);
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
    expect(msg).toMatch(/pick a symptom, sign, procedure, or situation/i);
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

  it("findAllValidationErrors returns an empty array for a well-formed tree", () => {
    expect(findAllValidationErrors(makeTree())).toEqual([]);
  });

  it("findAllValidationErrors returns a nodeId-less issue for a completely empty tree", () => {
    const issues = findAllValidationErrors(null);
    expect(issues).toHaveLength(1);
    expect(issues[0].nodeId).toBeNull();
    expect(issues[0].message).toMatch(/at least one condition/i);
  });

  it("findAllValidationErrors tags an empty group with its own node_id", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [{ kind: "OR", children: [] }],
    });
    const issues = findAllValidationErrors(tree);
    expect(issues).toHaveLength(1);
    expect(issues[0].nodeId).toBe(tree.children![0].node_id);
    expect(issues[0].message).toMatch(/empty/i);
  });

  it("findAllValidationErrors names empty pathway shells clearly", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [{ kind: "AND", pathway_key: "pw_a", children: [] }],
    });
    const issues = findAllValidationErrors(tree);
    expect(issues[0].message).toMatch(/situation has no conditions/i);
  });

  it("findWizardValidationErrors hides empty pathway shells mid-coding", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          pathway_key: "pw_a",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
          ],
        },
        { kind: "AND", pathway_key: "pw_b", children: [] },
      ],
    });
    expect(findAllValidationErrors(tree).some((i) => /situation has no conditions/i.test(i.message))).toBe(
      true,
    );
    expect(findWizardValidationErrors(tree)).toEqual([]);
  });

  it("pruneEmptyClusterShells drops empty lead/trailing AT_LEAST groups", () => {
    const tree = assignNodeIds({
      kind: "AND",
      pathway_key: "pw",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
        { kind: "AT_LEAST", min: 1, cluster_role: "trailing", children: [] },
      ],
    });
    const pruned = pruneEmptyClusterShells(tree);
    expect(pruned.children).toHaveLength(1);
    expect(pruned.children![0].kind).toBe("CONCEPT");
  });

  it("removing the last cluster child also removes the empty AT_LEAST shell", () => {
    const tree = assignNodeIds({
      kind: "AND",
      pathway_key: "pw",
      children: [
        {
          kind: "AT_LEAST",
          min: 1,
          cluster_role: "trailing",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
          ],
        },
      ],
    });
    const leafId = tree.children![0].children![0].node_id!;
    const updated = applyUpdate(tree, { kind: "remove", nodeId: leafId });
    expect(updated!.children).toEqual([]);
  });

  it("findAllValidationErrors collects every problem in the tree, not just the first", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "OR", children: [] },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "", preferred_term: "?" } },
        {
          kind: "AT_LEAST",
          min: 5,
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
          ],
        },
      ],
    });
    const issues = findAllValidationErrors(tree);
    expect(issues).toHaveLength(3);
    // Each issue points at a different offending node, in tree order.
    expect(issues[0].nodeId).toBe(tree.children![0].node_id);
    expect(issues[1].nodeId).toBe(tree.children![1].node_id);
    expect(issues[2].nodeId).toBe(tree.children![2].node_id);
    expect(issues[0].message).toMatch(/empty/i);
    expect(issues[1].message).toMatch(/pick a symptom/i);
    expect(issues[2].message).toMatch(/asking for more symptoms/i);
  });

  it("findAllValidationErrors and findValidationError agree on the first problem", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "OR", children: [] },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "", preferred_term: "?" } },
      ],
    });
    expect(findAllValidationErrors(tree)[0].message).toBe(findValidationError(tree));
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

  it("assignNodeIds promotes AI raw_term / source_text onto source_row_text", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "demographic" as unknown as "DEMOGRAPHIC",
          field: "age",
          operator: "<=",
          value: 24,
          unit: "years",
          raw_term: "children and young people",
        } as unknown as EditableLogicNode,
        {
          kind: "concept" as unknown as "CONCEPT",
          criterion: {
            snomed_concept_id: "30746006",
            preferred_term: "Lymphadenopathy (disorder)",
            source_text: "unexplained lymphadenopathy",
          } as unknown as EditableLogicNode["criterion"],
        },
      ],
    });
    expect(tree.children![0].source_row_text).toBe("children and young people");
    expect(tree.children![1].source_row_text).toBe("unexplained lymphadenopathy");
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

  it("stripNodeIds persists a non-empty source_row_text, trimmed", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "162031009", preferred_term: "Indigestion" },
          source_row_text: "  treatment-resistant dyspepsia  ",
        },
      ],
    });
    const stripped = stripNodeIds(tree);
    const concept = (stripped.children as Array<Record<string, unknown>>)[0];
    expect(concept.source_row_text).toBe("treatment-resistant dyspepsia");
  });

  it("stripNodeIds drops an empty/whitespace-only source_row_text", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "162031009", preferred_term: "Indigestion" },
          source_row_text: "   ",
        },
      ],
    });
    const stripped = stripNodeIds(tree);
    const concept = (stripped.children as Array<Record<string, unknown>>)[0];
    expect("source_row_text" in concept).toBe(false);
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
    // confidence-surfacing (highlight-to-build wizard): these two now
    // round-trip through save on purpose, unlike the rest of the LLM
    // provenance blob below -- see confidenceGate.ts for why stripping
    // them used to throw away the anti-rubber-stamp signal after the
    // first review pass.
    expect(crit.confidence).toBe(0.97);
    expect(crit.needs_human_review).toBe(false);

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
      "resolver_turns",
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

describe("addPrerequisiteToOrSymptoms / smart add_demographic", () => {
  function makeOrSymptoms(): EditableLogicNode {
    return assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "262285001",
            preferred_term: "Weight decreased",
          },
        },
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "84229001", preferred_term: "Fatigue" },
        },
        {
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "62315008",
            preferred_term: "Altered bowel function",
          },
        },
      ],
    });
  }

  it("detects OR root with symptom leaves only", () => {
    const tree = makeOrSymptoms();
    expect(isOrGroupSymptomsOnly(tree)).toBe(true);
    expect(hasOrRootSymptomsOnly(tree)).toBe(true);
  });

  it("add_demographic restructures OR symptoms into AND[demographic, OR[symptoms]]", () => {
    const tree = makeOrSymptoms();
    const updated = applyUpdate(tree, {
      kind: "add_demographic",
      parentNodeId: tree.node_id,
    });
    expect(updated!.kind).toBe("AND");
    const kids = updated!.children ?? [];
    expect(kids[0].kind).toBe("DEMOGRAPHIC");
    expect(kids[1].kind).toBe("OR");
    expect(kids[1].children).toHaveLength(3);
  });

  it("add_demographic on AND root still appends without restructuring", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
      ],
    });
    const updated = applyUpdate(tree, {
      kind: "add_demographic",
      parentNodeId: tree.node_id,
    });
    expect(updated!.kind).toBe("AND");
    expect(updated!.children).toHaveLength(2);
    expect(updated!.children!.some((c) => c.kind === "DEMOGRAPHIC")).toBe(true);
  });

  it("add_demographic with field sex appends under pathway AND without lifting to global", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "DEMOGRAPHIC",
          field: "age",
          operator: ">=",
          value: 55,
          unit: "years",
        },
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              pathway_key: "pw_a",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
                },
              ],
            },
            {
              kind: "AND",
              pathway_key: "pw_b",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" },
                },
              ],
            },
          ],
        },
      ],
    });
    const pathwayA = tree.children![1].children![0];
    const updated = applyUpdate(tree, {
      kind: "add_demographic",
      parentNodeId: pathwayA.node_id,
      field: "sex",
    });
    expect(updated!.kind).toBe("AND");
    const globalKids = updated!.children ?? [];
    expect(globalKids.filter((c) => c.kind === "DEMOGRAPHIC")).toHaveLength(1);
    expect(globalKids[0].field).toBe("age");
    const updatedPwA = globalKids[1].children![0];
    const sexLeaf = updatedPwA.children!.find((c) => c.kind === "DEMOGRAPHIC");
    expect(sexLeaf?.field).toBe("sex");
    expect(sexLeaf?.value).toBe("female");
    expect(globalKids[1].children![1].children!.some((c) => c.kind === "DEMOGRAPHIC")).toBe(
      false,
    );
  });

  it("add_demographic applies a prefill and source_row_text parsed from a highlighted phrase", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
      ],
    });
    const updated = applyUpdate(tree, {
      kind: "add_demographic",
      parentNodeId: tree.node_id,
      field: "age",
      prefill: { operator: ">=", value: "40", unit: "years" },
      sourceRowText: "aged 40 and over",
    });
    const demo = updated!.children!.find((c) => c.kind === "DEMOGRAPHIC");
    expect(demo?.operator).toBe(">=");
    expect(demo?.value).toBe("40");
    expect(demo?.unit).toBe("years");
    expect(demo?.source_row_text).toBe("aged 40 and over");
  });

  it("add_demographic with no prefill keeps the existing blank defaults", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
      ],
    });
    const updated = applyUpdate(tree, {
      kind: "add_demographic",
      parentNodeId: tree.node_id,
    });
    const demo = updated!.children!.find((c) => c.kind === "DEMOGRAPHIC");
    expect(demo?.operator).toBe(">=");
    expect(demo?.value).toBe(40);
    expect(demo?.source_row_text).toBeUndefined();
  });

  it("promoteOrPrerequisites leaves demos nested inside pathway ANDs untouched", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          children: [
            {
              kind: "DEMOGRAPHIC",
              field: "sex",
              operator: "=",
              value: "female",
              unit: null,
            },
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" },
            },
          ],
        },
      ],
    });
    expect(promoteOrPrerequisites(tree)).toBe(tree);
  });

  it("liftSharedPathwayDemographics lifts age shared by every pathway (NG12 1.1.2)", () => {
    const age = {
      kind: "DEMOGRAPHIC" as const,
      field: "age",
      operator: ">=",
      value: 40,
      unit: "years",
    };
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          children: [
            age,
            {
              kind: "AT_LEAST",
              min: 2,
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
                },
              ],
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: {
                snomed_concept_id: "2",
                preferred_term: "Ever smoked",
              },
            },
            {
              kind: "AT_LEAST",
              min: 1,
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
                },
              ],
            },
            { ...age },
          ],
        },
      ],
    });

    const lifted = liftSharedPathwayDemographics(tree);
    expect(lifted.kind).toBe("AND");
    expect(lifted.children![0].kind).toBe("DEMOGRAPHIC");
    expect(lifted.children![0].field).toBe("age");
    expect(lifted.children![0].value).toBe(40);
    expect(lifted.children![1].kind).toBe("OR");
    const pathways = lifted.children![1].children!;
    expect(pathways).toHaveLength(2);
    for (const pathway of pathways) {
      expect(pathway.children!.some((c) => c.kind === "DEMOGRAPHIC")).toBe(false);
    }
    expect(pathways[0].children!.some((c) => c.kind === "AT_LEAST" && c.min === 2)).toBe(
      true,
    );
    expect(pathways[1].children!.some((c) => c.kind === "AT_LEAST" && c.min === 1)).toBe(
      true,
    );
  });

  it("liftSharedPathwayDemographics leaves pathway-local demos alone", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          children: [
            {
              kind: "DEMOGRAPHIC",
              field: "sex",
              operator: "=",
              value: "female",
              unit: null,
            },
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" },
            },
          ],
        },
      ],
    });
    expect(liftSharedPathwayDemographics(tree)).toBe(tree);
  });

  it("addPrerequisiteToOrSymptoms preserves all symptom nodes", () => {
    const tree = makeOrSymptoms();
    const prereq = assignNodeIds({
      kind: "DEMOGRAPHIC",
      field: "sex",
      operator: "=",
      value: "female",
      unit: null,
    });
    const fixed = addPrerequisiteToOrSymptoms(tree, prereq);
    expect(fixed.kind).toBe("AND");
    expect(fixed.children![0].field).toBe("sex");
    expect(fixed.children![1].children).toHaveLength(3);
  });
});

describe("pathway_key stable identity", () => {
  function makePathwaySplitTree(): EditableLogicNode {
    return assignNodeIds({
      kind: "AND",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
        {
          kind: "OR",
          children: [
            { kind: "AND", children: [{ kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } }] },
            { kind: "AND", children: [{ kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "B" } }] },
          ],
        },
      ],
    });
  }

  it("mintPathwayKey returns distinct keys on successive calls", () => {
    const a = mintPathwayKey();
    const b = mintPathwayKey();
    expect(a).not.toBe(b);
    expect(a.startsWith("pw_")).toBe(true);
  });

  it("ensurePathwayKeys backfills a key onto every pathway that lacks one", () => {
    const tree = makePathwaySplitTree();
    const keyed = ensurePathwayKeys(tree);
    const orNode = keyed.children!.find((c) => c.kind === "OR")!;
    const keys = orNode.children!.map((c) => c.pathway_key);
    expect(keys.every((k) => typeof k === "string" && k.length > 0)).toBe(true);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("ensurePathwayKeys leaves an already-keyed pathway untouched", () => {
    const tree = makePathwaySplitTree();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    orNode.children![0].pathway_key = "pw_existing";
    const keyed = ensurePathwayKeys(tree);
    const reKeyedOr = keyed.children!.find((c) => c.kind === "OR")!;
    expect(reKeyedOr.children![0].pathway_key).toBe("pw_existing");
    expect(reKeyedOr.children![1].pathway_key).toBeTruthy();
    expect(reKeyedOr.children![1].pathway_key).not.toBe("pw_existing");
  });

  it("ensurePathwayKeys is a no-op on a tree with no pathway split", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [{ kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } }],
    });
    const keyed = ensurePathwayKeys(tree);
    expect(keyed).toEqual(tree);
  });

  it("add_group on a pathway-split OR mints a fresh pathway_key on the new pathway", () => {
    const tree = ensurePathwayKeys(makePathwaySplitTree());
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const updated = applyUpdate(tree, {
      kind: "add_group",
      parentNodeId: orNode.node_id,
      groupKind: "AND",
    });
    const updatedOr = updated!.children!.find((c) => c.kind === "OR")!;
    expect(updatedOr.children).toHaveLength(3);
    const newPathway = updatedOr.children![2];
    expect(newPathway.pathway_key).toBeTruthy();
    const allKeys = updatedOr.children!.map((c) => c.pathway_key);
    expect(new Set(allKeys).size).toBe(3);
  });

  it("add_group on a non-pathway parent does not set pathway_key", () => {
    const tree = assignNodeIds({ kind: "AND", children: [] });
    const updated = applyUpdate(tree, {
      kind: "add_group",
      parentNodeId: tree.node_id,
      groupKind: "OR",
    });
    expect(updated!.children![0].pathway_key).toBeUndefined();
  });

  it("stripNodeIds preserves pathway_key but not node_id", () => {
    const tree = ensurePathwayKeys(makePathwaySplitTree());
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const stripped = stripNodeIds(orNode.children![0]);
    expect(stripped.pathway_key).toBe(orNode.children![0].pathway_key);
    expect(stripped.node_id).toBeUndefined();
  });

  it("stripNodeIds omits pathway_key entirely on nodes that never had one", () => {
    const tree = assignNodeIds({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "A" },
    });
    const stripped = stripNodeIds(tree);
    expect("pathway_key" in stripped).toBe(false);
  });
});

describe("split_pathway / merge_pathways", () => {
  function makeFourSymptomPathway(): EditableLogicNode {
    // A single pathway (AND child of the OR) with 4 CONCEPT leaves,
    // pre-keyed, ready to split.
    return ensurePathwayKeys(
      assignNodeIds({
        kind: "AND",
        children: [
          { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
          {
            kind: "OR",
            children: [
              {
                kind: "AND",
                children: [
                  { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Nausea" } },
                  { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" } },
                  { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "Weight loss" } },
                  { kind: "CONCEPT", criterion: { snomed_concept_id: "4", preferred_term: "Reflux" } },
                ],
              },
              {
                kind: "AND",
                children: [
                  { kind: "CONCEPT", criterion: { snomed_concept_id: "5", preferred_term: "Haemoptysis" } },
                ],
              },
            ],
          },
        ],
      }),
    );
  }

  it("split_pathway partitions children at splitAt into two new sibling pathways", () => {
    const tree = makeFourSymptomPathway();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const targetPathway = orNode.children![0];
    const originalKey = targetPathway.pathway_key;

    const updated = applyUpdate(tree, {
      kind: "split_pathway",
      nodeId: targetPathway.node_id,
      splitAt: 2,
    })!;
    const updatedOr = updated.children!.find((c) => c.kind === "OR")!;
    expect(updatedOr.children).toHaveLength(3);

    const [first, second, untouched] = updatedOr.children!;
    expect(first.children).toHaveLength(2);
    expect(second.children).toHaveLength(2);
    expect(first.children!.map((c) => c.criterion?.snomed_concept_id)).toEqual(["1", "2"]);
    expect(second.children!.map((c) => c.criterion?.snomed_concept_id)).toEqual(["3", "4"]);
    expect(untouched.children).toHaveLength(1);
    expect(untouched.children![0].criterion?.snomed_concept_id).toBe("5");

    // New pathways get fresh, distinct keys; the original is retired.
    expect(first.pathway_key).toBeTruthy();
    expect(second.pathway_key).toBeTruthy();
    expect(first.pathway_key).not.toBe(second.pathway_key);
    expect(first.pathway_key).not.toBe(originalKey);
    expect(second.pathway_key).not.toBe(originalKey);
  });

  it("split_pathway is a no-op when splitAt would leave one side empty", () => {
    const tree = makeFourSymptomPathway();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const singleLeafPathway = orNode.children![1];

    const updated = applyUpdate(tree, {
      kind: "split_pathway",
      nodeId: singleLeafPathway.node_id,
      splitAt: 1,
    })!;
    expect(updated).toEqual(tree);
  });

  it("merge_pathways concatenates two siblings' children into one new pathway", () => {
    const tree = makeFourSymptomPathway();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const [pathwayA, pathwayB] = orNode.children!;

    const updated = applyUpdate(tree, {
      kind: "merge_pathways",
      firstNodeId: pathwayA.node_id,
      secondNodeId: pathwayB.node_id,
    })!;
    const updatedOr = updated.children!.find((c) => c.kind === "OR")!;
    expect(updatedOr.children).toHaveLength(1);

    const merged = updatedOr.children![0];
    expect(merged.children!.map((c) => c.criterion?.snomed_concept_id)).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
    ]);
    expect(merged.pathway_key).toBeTruthy();
    expect(merged.pathway_key).not.toBe(pathwayA.pathway_key);
    expect(merged.pathway_key).not.toBe(pathwayB.pathway_key);
  });

  it("a confirmed leaf's node_id and criterion survive a split-then-merge round-trip", () => {
    const tree = makeFourSymptomPathway();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const targetPathway = orNode.children![0];
    const originalLeafIds = targetPathway.children!.map((c) => c.node_id);
    const originalConceptIds = targetPathway.children!.map((c) => c.criterion?.snomed_concept_id);

    const afterSplit = applyUpdate(tree, {
      kind: "split_pathway",
      nodeId: targetPathway.node_id,
      splitAt: 2,
    })!;
    const orAfterSplit = afterSplit.children!.find((c) => c.kind === "OR")!;
    const [firstHalf, secondHalf] = orAfterSplit.children!;

    const afterMerge = applyUpdate(afterSplit, {
      kind: "merge_pathways",
      firstNodeId: firstHalf.node_id,
      secondNodeId: secondHalf.node_id,
    })!;
    const orAfterMerge = afterMerge.children!.find((c) => c.kind === "OR")!;
    const rebuiltPathway = orAfterMerge.children![0];

    expect(rebuiltPathway.children!.map((c) => c.node_id)).toEqual(originalLeafIds);
    expect(rebuiltPathway.children!.map((c) => c.criterion?.snomed_concept_id)).toEqual(
      originalConceptIds,
    );
  });

  it("merge_pathways is a no-op when the two ids are not siblings", () => {
    const tree = makeFourSymptomPathway();
    const orNode = tree.children!.find((c) => c.kind === "OR")!;
    const pathwayA = orNode.children![0];
    const leafInsideA = pathwayA.children![0];

    const updated = applyUpdate(tree, {
      kind: "merge_pathways",
      firstNodeId: pathwayA.node_id,
      secondNodeId: leafInsideA.node_id,
    })!;
    expect(updated).toEqual(tree);
  });
});
