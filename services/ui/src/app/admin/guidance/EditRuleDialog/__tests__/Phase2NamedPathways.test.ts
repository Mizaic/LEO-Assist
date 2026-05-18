/**
 * Phase 2 of the edit-rule wizard redesign: optional pathway names.
 *
 * Each group node may carry an optional plain-English ``name``. A
 * named OR-child reads as "Possible cancer" instead of "Pathway A".
 * The name must round-trip through the editor's serialise / parse
 * helpers so a save-then-reload preserves it, and the read-only
 * sentence renderer must use it as the headline when set.
 *
 * Atlas trace:
 *   DI: DI-2E01CC45
 *   DO: DO-E67AFBE2
 *   VT: VT-8C96CBC0
 */
import { applyUpdate, assignNodeIds, stripNodeIds } from "../treeOps";
import type { LogicNodeSeed } from "../treeOps";
import { treeToSentence } from "../treeToSentence";
import type { EditableLogicNode } from "../types";

function tree(node: LogicNodeSeed): EditableLogicNode {
  return assignNodeIds(node);
}

describe("Phase 2: optional pathway names", () => {
  it("preserves a name set on a group when stripping for the API", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "Possible cancer",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
            },
          ],
        },
      ],
    });
    const wire = stripNodeIds(root);
    const children = (wire as { children: Array<Record<string, unknown>> })
      .children;
    expect(children[0].name).toBe("Possible cancer");
    expect(children[1].name).toBeUndefined();
  });

  it("trims whitespace and drops empty names from the wire format", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "   ",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
        {
          kind: "AND",
          name: "  Symptom watch  ",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
            },
          ],
        },
      ],
    });
    const children = (
      stripNodeIds(root) as { children: Array<Record<string, unknown>> }
    ).children;
    expect(children[0].name).toBeUndefined();
    expect(children[1].name).toBe("Symptom watch");
  });

  it("survives a round-trip through stripNodeIds + assignNodeIds", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "Cancer pathway",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
      ],
    });
    const wire = stripNodeIds(root) as LogicNodeSeed;
    const reloaded = assignNodeIds(wire);
    expect(reloaded.children?.[0].name).toBe("Cancer pathway");
  });

  it("uses the name as the pathway headline in treeToSentence", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "Possible cancer",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
            },
          ],
        },
      ],
    });
    const result = treeToSentence(root);
    expect(result.pathways?.[0].headline).toBe("Possible cancer");
    expect(result.pathways?.[1].headline).toBe("Pathway B");
  });

  it("falls back to the positional letter when name is missing or whitespace", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "   ",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
            },
          ],
        },
      ],
    });
    const result = treeToSentence(root);
    expect(result.pathways?.[0].headline).toBe("Pathway A");
    expect(result.pathways?.[1].headline).toBe("Pathway B");
  });

  it("set_name update applies and clearing it removes the field", () => {
    const root = tree({
      kind: "OR",
      children: [
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
            },
          ],
        },
      ],
    });
    const child = root.children![0];
    const named = applyUpdate(root, {
      kind: "set_name",
      nodeId: child.node_id,
      name: "  Possible cancer  ",
    });
    expect(named?.children?.[0].name).toBe("Possible cancer");

    const cleared = applyUpdate(named!, {
      kind: "set_name",
      nodeId: child.node_id,
      name: "",
    });
    expect(cleared?.children?.[0].name).toBeUndefined();
  });

  it("set_name is a no-op on leaf nodes (CONCEPT / DEMOGRAPHIC)", () => {
    const root = tree({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
      ],
    });
    const concept = root.children![0];
    const result = applyUpdate(root, {
      kind: "set_name",
      nodeId: concept.node_id,
      name: "Should not stick",
    });
    expect(result?.children?.[0].name).toBeUndefined();
  });
});
