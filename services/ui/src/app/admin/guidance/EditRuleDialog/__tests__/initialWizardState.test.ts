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

  it("infers AT_LEAST for a pathway that already has a trailing or lead subgroup", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              pathway_key: "a",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Raised platelets" },
                },
                {
                  kind: "AT_LEAST",
                  min: 1,
                  cluster_role: "trailing",
                  children: [
                    { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Nausea" } },
                  ],
                },
              ],
            },
            {
              kind: "AND",
              pathway_key: "b",
              children: [
                {
                  kind: "AT_LEAST",
                  min: 1,
                  cluster_role: "lead",
                  children: [
                    { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "Vomiting" } },
                  ],
                },
              ],
            },
          ],
        },
      ],
    }) as EditableLogicNode;
    const state = buildInitialWizardState(tree, "raised platelets with nausea or vomiting");

    expect(state.step).toBe("review");
    expect(state.clusterGroupings).toEqual({ a: "AT_LEAST" });
    expect(state.leadClusterGroupings).toEqual({ b: "AT_LEAST" });
  });

  it("leaves grouping unset for a pathway with no subgroup -- never guesses AND", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              pathway_key: "a",
              children: [
                { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Nausea" } },
              ],
            },
            {
              kind: "AND",
              pathway_key: "b",
              children: [
                { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" } },
              ],
            },
          ],
        },
      ],
    }) as EditableLogicNode;
    const state = buildInitialWizardState(tree, "people with nausea or vomiting");

    expect(state.step).toBe("review");
    expect(state.clusterGroupings).toEqual({});
    expect(state.leadClusterGroupings).toEqual({});
  });
});
