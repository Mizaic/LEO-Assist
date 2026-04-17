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
  stripNodeIds,
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
});
