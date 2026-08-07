/**
 * Age x lab bands attach beside Always-true prerequisites.
 * Atlas: DI-E5B04297 / DO-C38E6184 / VT-409A9A74
 */
import { attachAgeLabBandOr } from "../HighlightWizard/attachAgeLabBands";
import { buildAgeLabBandTree } from "../HighlightWizard/ageLabBands";
import type { EditableLogicNode } from "../types";

const symptom: EditableLogicNode = {
  node_id: "symptom-1",
  kind: "CONCEPT",
  criterion: {
    snomed_concept_id: "1",
    preferred_term: "possible symptoms of prostate cancer",
    term: "possible symptoms of prostate cancer",
    seeds: [],
  },
};

const psaBands = buildAgeLabBandTree({
  observableId: "102097009",
  observableTerm: "Serum PSA",
  unit: "ug/L",
  operator: ">",
  bands: [
    { ageFrom: "40", ageTo: "49", value: "2" },
    { ageFrom: "50", ageTo: "59", value: "3.5" },
  ],
});

describe("attachAgeLabBandOr", () => {
  it("keeps Always-true symptoms and adds the age/lab OR beside them", () => {
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [symptom],
    };
    const next = attachAgeLabBandOr(tree, psaBands);
    expect(next.kind).toBe("AND");
    expect(next.children).toHaveLength(2);
    expect(next.children![0]).toMatchObject({
      kind: "CONCEPT",
      node_id: "symptom-1",
    });
    expect(next.children![1]).toMatchObject({ kind: "OR" });
    expect(next.children![1]!.children).toHaveLength(2);
  });

  it("replaces an existing pathway OR without dropping prerequisites", () => {
    const oldOr: EditableLogicNode = {
      node_id: "old-or",
      kind: "OR",
      children: [
        {
          node_id: "pw-a",
          kind: "AND",
          pathway_key: "a",
          children: [],
        },
        {
          node_id: "pw-b",
          kind: "AND",
          pathway_key: "b",
          children: [],
        },
      ],
    };
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [symptom, oldOr],
    };
    const next = attachAgeLabBandOr(tree, psaBands);
    expect(next.children![0]).toMatchObject({ node_id: "symptom-1" });
    expect(next.children![1]).toBe(psaBands);
  });
});
