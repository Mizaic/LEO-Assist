/**
 * Reopen-at-Review when the logic tree is already built.
 */
import { buildInitialWizardState } from "../HighlightWizard/initialWizardState";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";

describe("buildInitialWizardState", () => {
  it("starts at prerequisites when pathways are empty shells", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            { kind: "AND", pathway_key: "a", children: [] },
            { kind: "AND", pathway_key: "b", children: [] },
          ],
        },
      ],
    });
    const state = buildInitialWizardState(tree, "a or b");
    expect(state.step).toBe("prerequisites");
  });

  it("starts at review when every multi-pathway already has leaves", () => {
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
              pathway_key: "a",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Nausea" },
                },
              ],
            },
            {
              kind: "AND",
              pathway_key: "b",
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
    }) as EditableLogicNode;
    const text = "people with nausea or vomiting";
    const state = buildInitialWizardState(tree, text);
    expect(state.step).toBe("review");
    expect(state.boundaries).toHaveLength(2);
  });
});
