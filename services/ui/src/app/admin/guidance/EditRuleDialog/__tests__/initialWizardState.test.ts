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

  it("rebuilds tree-sourced boundaries when the sentence has no pathway split (table-driven)", () => {
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
                  kind: "DEMOGRAPHIC",
                  field: "age",
                  operator: "between",
                  value: 40,
                  value2: 49,
                  unit: "years",
                },
                {
                  kind: "OBSERVATION",
                  observation: {
                    observable_id: "101",
                    observable_term: "Cancer antigen 125",
                    operator: ">=",
                    value: 35,
                    unit: "IU/ml",
                    within_days: 365,
                  },
                },
              ],
            },
            {
              kind: "AND",
              pathway_key: "b",
              children: [
                {
                  kind: "DEMOGRAPHIC",
                  field: "age",
                  operator: "between",
                  value: 50,
                  value2: 59,
                  unit: "years",
                },
                {
                  kind: "OBSERVATION",
                  observation: {
                    observable_id: "101",
                    observable_term: "Cancer antigen 125",
                    operator: ">=",
                    value: 31,
                    unit: "IU/ml",
                    within_days: 365,
                  },
                },
              ],
            },
          ],
        },
      ],
    }) as EditableLogicNode;
    const text =
      "1.5.9 Arrange an urgent ultrasound depending on age and serum CA125 according to the thresholds in table 1.";
    const state = buildInitialWizardState(tree, text);

    expect(state.step).toBe("review");
    expect(state.boundaries).toHaveLength(2);
    expect(state.boundaries?.every((b) => b.source === "tree")).toBe(true);
    expect(state.boundaries?.[0].text).toMatch(/40/);
    expect(state.boundaries?.[0].text).not.toMatch(/^Situation /);
    expect(state.boundaries?.[1].text).toMatch(/50/);
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
