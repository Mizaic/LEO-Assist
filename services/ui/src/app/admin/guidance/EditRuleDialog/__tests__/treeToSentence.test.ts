import { treeToSentence } from "../treeToSentence";
import { assignNodeIds } from "../treeOps";
import type { LogicNodeSeed } from "../treeOps";
import type { EditableLogicNode } from "../types";

function tree(node: LogicNodeSeed): EditableLogicNode {
  return assignNodeIds(node);
}

describe("treeToSentence", () => {
  it("renders an empty tree with a friendly call to action", () => {
    const result = treeToSentence(null);
    expect(result.lead).toMatch(/no conditions yet/i);
    expect(result.lead).toMatch(/add a symptom/i);
    expect(result.isWellShaped).toBe(false);
  });

  it("renders a single CONCEPT leaf", () => {
    const root = tree({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Cough (finding)" },
    });
    const result = treeToSentence(root);
    expect(result.lead).toBe("Applies to patients who has cough.");
  });

  it("renders an age >= demographic with plain English", () => {
    const root = tree({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: ">=",
      value: 40,
      unit: "years",
    });
    expect(treeToSentence(root).lead).toBe(
      "Applies to patients who is 40 years or older.",
    );
  });

  it("renders sex = female as plain English", () => {
    const root = tree({
      kind: "DEMOGRAPHIC",
      field: "sex",
      operator: "=",
      value: "female",
    });
    expect(treeToSentence(root).lead).toBe(
      "Applies to patients who is female.",
    );
  });

  it("flattens an AND of demographic + concept into one sentence", () => {
    const root = tree({
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
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
      ],
    });
    expect(treeToSentence(root).lead).toMatch(
      /is 40 years or older and has cough/i,
    );
  });

  it("renders an AT-LEAST cluster as a comma list with 'or'", () => {
    const root = tree({
      kind: "AT_LEAST",
      min: 2,
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
        },
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "3", preferred_term: "Dyspnea" },
        },
      ],
    });
    expect(treeToSentence(root).lead).toBe(
      "Applies to patients who has at least 2 of: cough, fatigue, or dyspnea.",
    );
  });

  it("recognises the AND[Demo*, OR[pathways]] shape and emits pathway bullets", () => {
    const root = tree({
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
              kind: "AND",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
                },
                {
                  kind: "CONCEPT",
                  criterion: {
                    snomed_concept_id: "2",
                    preferred_term: "Haemoptysis",
                  },
                },
              ],
            },
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "3", preferred_term: "Weight loss" },
            },
          ],
        },
      ],
    });
    const result = treeToSentence(root);
    expect(result.lead).toMatch(/40 years or older/i);
    expect(result.lead).toMatch(/match one of these pathways/i);
    expect(result.pathways).toHaveLength(2);
    expect(result.pathways?.[0]).toMatchObject({
      headline: "Pathway A",
      conditions: ["has cough", "has haemoptysis"],
    });
    expect(result.pathways?.[1]).toMatchObject({
      headline: "Pathway B",
      connector: "OR",
      conditions: ["has weight loss"],
    });
  });

  it("does not use technical jargon in any rendered text (health-literacy gate)", () => {
    const root = tree({
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
              kind: "AT_LEAST",
              min: 2,
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
                },
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
                },
              ],
            },
          ],
        },
      ],
    });
    const result = treeToSentence(root);
    const all = [
      result.lead,
      ...(result.pathways ?? []).flatMap((p) => [
        p.headline,
        p.connector,
        ...p.conditions,
      ]),
    ].join(" ");
    expect(all).not.toMatch(/SNOMED/i);
    expect(all).not.toMatch(/AT_LEAST/);
    expect(all).not.toMatch(/DEMOGRAPHIC/);
    expect(all).not.toMatch(/criterion/i);
  });
});
