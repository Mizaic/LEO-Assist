import {
  clinicalRowCore,
  leafResolvesRowText,
  matchCoversClinicalRow,
} from "../HighlightWizard/rowLeafResolve";
import type { EditableLogicNode } from "../types";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";

function concept(
  term: string,
  preferred = `${term} (finding)`,
): EditableLogicNode {
  return {
    node_id: term,
    kind: "CONCEPT",
    criterion: {
      snomed_concept_id: "1",
      preferred_term: preferred,
      term,
      semantic_tag: "finding",
    },
  };
}

function row(text: string, start = 0): RecommendationStructureItem {
  return { text, start, end: start + text.length };
}

describe("clinicalRowCore", () => {
  it("strips leading have/are and trailing NICE citations", () => {
    expect(clinicalRowCore("have dysphagia")).toBe("dysphagia");
    expect(
      clinicalRowCore("dyspepsia. [2015, amended 2025]"),
    ).toBe("dyspepsia");
    expect(
      clinicalRowCore("appetite loss. [2015]"),
    ).toBe("appetite loss");
  });
});

describe("leafResolvesRowText", () => {
  it("matches tag-stripped preferred terms to short list rows", () => {
    expect(leafResolvesRowText(concept("cough"), row("cough"))).toBe(true);
  });

  it("matches UK/US and reordered appetite/breath synonyms", () => {
    expect(
      leafResolvesRowText(concept("dyspnoea", "Dyspnea (finding)"), row("shortness of breath")),
    ).toBe(true);
    expect(
      leafResolvesRowText(
        concept("loss of appetite", "Loss of appetite (finding)"),
        row("appetite loss. [2015]"),
      ),
    ).toBe(true);
  });

  it("matches reflux to acid reflux without claiming unrelated rows", () => {
    expect(
      leafResolvesRowText(
        concept("Acid reflux", "Acid reflux (finding)"),
        row("reflux"),
      ),
    ).toBe(true);
    expect(
      leafResolvesRowText(concept("cough"), row("fatigue")),
    ).toBe(false);
  });

  it("matches NG12 1.1.2's 'ever smoked' row to the leaf's more specific 'ever smoked tobacco' term", () => {
    expect(
      leafResolvesRowText(
        concept("ever smoked tobacco", "Finding of tobacco smoking consumption (finding)"),
        row("ever smoked"),
      ),
    ).toBe(true);
  });

  it("does not let a short preferred term claim a longer clinical row", () => {
    const weightOnly: EditableLogicNode = {
      node_id: "w",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "9",
        preferred_term: "Weight",
        term: "weight",
      },
    };
    expect(leafResolvesRowText(weightOnly, row("weight loss"))).toBe(false);
  });

  it("matches chest X-ray wording across hyphen and suggest/suggestive drift", () => {
    const leaf = concept(
      "chest X-ray findings suggestive of lung cancer",
      "Lung mass (finding)",
    );
    expect(
      leafResolvesRowText(
        leaf,
        row("have chest X\u2011ray findings that suggest lung cancer"),
      ),
    ).toBe(true);
  });
});

describe("matchCoversClinicalRow", () => {
  it("accepts an exact clinical token inside a have-prefixed row", () => {
    const text = "have dysphagia";
    expect(
      matchCoversClinicalRow(
        {
          start: 5,
          end: 14,
          matchedText: "dysphagia",
          strategy: "exact",
          score: 1,
        },
        row(text),
      ),
    ).toBe(true);
  });
});
