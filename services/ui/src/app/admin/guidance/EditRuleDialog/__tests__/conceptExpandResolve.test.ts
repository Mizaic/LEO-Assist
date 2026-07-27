import {
  buildResolvedTermRow,
  criteriaFromResolvedRows,
  rowToCriterion,
} from "../conceptExpandResolve";
import type { ConceptSearchHit } from "../types";

const hit = (id: string, term: string): ConceptSearchHit => ({
  snomed_concept_id: id,
  term,
  semantic_tag: "finding",
});

describe("buildResolvedTermRow", () => {
  it("flags zero matches", () => {
    const row = buildResolvedTermRow("cough", []);
    expect(row.status).toBe("unmatched");
    expect(row.selectedId).toBeNull();
  });

  it("auto-picks a single match", () => {
    const row = buildResolvedTermRow("cough", [hit("1", "Cough")]);
    expect(row.status).toBe("matched");
    expect(row.selectedId).toBe("1");
  });

  it("leaves multi-match rows editable with the top hit selected", () => {
    const row = buildResolvedTermRow("cough", [
      hit("1", "Cough"),
      hit("2", "Productive cough"),
    ]);
    expect(row.status).toBe("needs_pick");
    expect(row.selectedId).toBe("1");
  });
});

describe("criteriaFromResolvedRows", () => {
  it("skips unmatched rows and maps selected hits", () => {
    const rows = [
      buildResolvedTermRow("cough", [hit("1", "Cough")]),
      buildResolvedTermRow("mystery", []),
      buildResolvedTermRow("fatigue", [
        hit("3", "Fatigue"),
        hit("4", "Tiredness"),
      ]),
    ];
    const criteria = criteriaFromResolvedRows(rows);
    expect(criteria).toHaveLength(2);
    expect(criteria[0].snomed_concept_id).toBe("1");
    expect(criteria[1].snomed_concept_id).toBe("3");
  });

  it("rowToCriterion returns null without a selection", () => {
    expect(rowToCriterion(buildResolvedTermRow("x", []))).toBeNull();
  });
});
