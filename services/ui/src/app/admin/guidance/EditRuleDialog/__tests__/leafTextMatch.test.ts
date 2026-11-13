/**
 * Unit tests for leafTextMatch -- the shared "where does this leaf's
 * value live in the verbatim text?" helper used by both
 * StepPrerequisites (Step 1) and the wizard orchestrator (Step 3).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import {
  collectTreeHighlights,
  demographicMatchCandidate,
  leafTextMatch,
  leafTextMatches,
} from "../HighlightWizard/leafTextMatch";
import type { EditableLogicNode } from "../types";

const TEXT =
  "Consider non-urgent referral in people aged 55 or over with " +
  "weight loss and nausea.";

function makeNode(overrides: Partial<EditableLogicNode>): EditableLogicNode {
  return { node_id: "n1", kind: "CONCEPT", ...overrides };
}

describe("demographicMatchCandidate", () => {
  it("builds an 'or over' phrase for >=", () => {
    const node = makeNode({ kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "55" });
    expect(demographicMatchCandidate(node)).toBe("aged 55 or over");
  });

  it("builds a range phrase for between", () => {
    const node = makeNode({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: "between",
      value: "18",
      value2: "40",
    });
    expect(demographicMatchCandidate(node)).toBe("18 to 40");
  });

  it("maps sex m/f to male/female", () => {
    const node = makeNode({ kind: "DEMOGRAPHIC", field: "sex", value: "f" });
    expect(demographicMatchCandidate(node)).toBe("female");
  });

  it("returns null with no value", () => {
    const node = makeNode({ kind: "DEMOGRAPHIC", field: "age", operator: ">=" });
    expect(demographicMatchCandidate(node)).toBeNull();
  });
});

describe("leafTextMatch", () => {
  it("anchors a DEMOGRAPHIC age leaf onto the verbatim text", () => {
    const node = makeNode({ kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "55" });
    const match = leafTextMatch(TEXT, node);
    expect(match).not.toBeNull();
    expect(TEXT.slice(match!.start, match!.end)).toBe("aged 55 or over");
  });

  it("anchors age < 50 onto NICE 'aged under 50' (NG12 1.3.1 E)", () => {
    const ng =
      "aged under 50 with rectal bleeding and either of the following unexplained symptoms:";
    const node = makeNode({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: "<",
      value: "50",
    });
    const match = leafTextMatch(ng, node);
    expect(match).not.toBeNull();
    expect(ng.slice(match!.start, match!.end)).toBe("aged under 50");
  });

  it("anchors age <= 24 onto NICE 'children and young people' (NG12 1.10.2)", () => {
    const ng =
      "1.10.2 Refer children and young people for immediate specialist " +
      "assessment for leukaemia if they have unexplained petechiae or " +
      "hepatosplenomegaly. [2015]";
    const node = makeNode({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: "<=",
      value: "24",
    });
    const match = leafTextMatch(ng, node);
    expect(match).not.toBeNull();
    expect(ng.slice(match!.start, match!.end)).toBe("children and young people");
  });

  it("anchors a CONCEPT leaf by its preferred_term", () => {
    const node = makeNode({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
    });
    const match = leafTextMatch(TEXT, node);
    expect(match).not.toBeNull();
    expect(TEXT.slice(match!.start, match!.end).toLowerCase()).toBe("weight loss");
  });

  // Regression: a SNOMED preferred term often shares no words with the
  // guideline row it was picked for ("Indigestion" for "treatment-
  // resistant dyspepsia"). Without preferring source_row_text, the
  // quote-panel highlighter silently skips those words -- exactly the
  // "missing highlights" reported against NG12 1.2.9 Step 2.
  it("prefers source_row_text over preferred_term when the SNOMED label does not appear in the guideline", () => {
    const NG =
      "Consider endoscopy for treatment-resistant dyspepsia, or upper abdominal pain.";
    const node = makeNode({
      kind: "CONCEPT",
      source_row_text: "treatment-resistant dyspepsia",
      criterion: {
        snomed_concept_id: "162031009",
        preferred_term: "Indigestion",
      },
    });
    const match = leafTextMatch(NG, node);
    expect(match).not.toBeNull();
    expect(NG.slice(match!.start, match!.end)).toBe("treatment-resistant dyspepsia");
  });

  it("anchors an OBSERVATION leaf by its observable_term", () => {
    const node = makeNode({
      kind: "OBSERVATION",
      observation: {
        observable_id: "obs-1",
        observable_term: "nausea",
        operator: ">=",
        value: 1,
        unit: "",
      },
    });
    const match = leafTextMatch(TEXT, node);
    expect(match).not.toBeNull();
    expect(TEXT.slice(match!.start, match!.end).toLowerCase()).toBe("nausea");
  });

  it("returns null for a leaf kind with no verbatim wording (RULE_FIRED)", () => {
    const node = makeNode({ kind: "RULE_FIRED", referenced_rule_id: "r1" });
    expect(leafTextMatch(TEXT, node)).toBeNull();
  });

  it("returns null when there is no recommendation text at all", () => {
    const node = makeNode({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
    });
    expect(leafTextMatch(null, node)).toBeNull();
  });
});

// Regression: a multi-seed CONCEPT leaf ("Add another code that means
// the same") must anchor onto EVERY seed's wording, not just the
// headline term -- otherwise a leaf capturing several findings looks
// like it barely captured any of them.
describe("leafTextMatches", () => {
  it("returns one match per single-seed CONCEPT leaf, same as leafTextMatch", () => {
    const node = makeNode({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
    });
    const matches = leafTextMatches(TEXT, node);
    expect(matches.length).toBe(1);
    expect(TEXT.slice(matches[0].start, matches[0].end).toLowerCase()).toBe("weight loss");
  });

  it("returns a match for every seed of a multi-seed CONCEPT leaf", () => {
    const node = makeNode({
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "1",
        preferred_term: "Weight loss",
        seeds: [
          { snomed_concept_id: "1", preferred_term: "Weight loss" },
          { snomed_concept_id: "2", preferred_term: "Nausea" },
        ],
      },
    });
    const matches = leafTextMatches(TEXT, node);
    const words = matches.map((m) => TEXT.slice(m.start, m.end).toLowerCase());
    expect(words).toEqual(expect.arrayContaining(["weight loss", "nausea"]));
  });

  it("returns an empty array for a leaf kind with no verbatim wording", () => {
    const node = makeNode({ kind: "RULE_FIRED", referenced_rule_id: "r1" });
    expect(leafTextMatches(TEXT, node)).toEqual([]);
  });

  it("highlights every contiguous piece of a disconnected source_row_text (NG12 1.5.17)", () => {
    const ng12 =
      "1.5.17 Consider a suspected cancer pathway referral for vulval cancer " +
      "in women who have an unexplained vulval lump, ulceration or bleeding. [2015]";
    const node = makeNode({
      kind: "CONCEPT",
      source_row_text: "unexplained vulval bleeding.",
      criterion: {
        snomed_concept_id: "890094005",
        preferred_term: "Bleeding from genital region (finding)",
      },
    });
    const matches = leafTextMatches(ng12, node);
    const pieces = matches.map((m) => ng12.slice(m.start, m.end));
    expect(pieces).toEqual(["unexplained vulval", "bleeding."]);
  });
});

describe("collectTreeHighlights", () => {
  it("finds every anchorable leaf across a nested tree, as confirmed spans", () => {
    const tree = makeNode({
      kind: "AND",
      children: [
        makeNode({ kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "55" }),
        {
          node_id: "n2",
          kind: "AT_LEAST",
          children: [
            makeNode({
              node_id: "n3",
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
            }),
            {
              node_id: "n4",
              kind: "OBSERVATION",
              observation: {
                observable_id: "obs-1",
                observable_term: "nausea",
                operator: ">=",
                value: 1,
                unit: "",
              },
            },
          ],
        },
      ],
    });

    const spans = collectTreeHighlights(TEXT, tree);
    const words = spans.map((s) => TEXT.slice(s.start, s.end).toLowerCase());

    expect(spans.every((s) => s.kind === "confirmed")).toBe(true);
    expect(words).toEqual(
      expect.arrayContaining(["aged 55 or over", "weight loss", "nausea"]),
    );
  });

  it("emits a highlight span for every seed of a multi-seed CONCEPT leaf, not just one", () => {
    const tree = makeNode({
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "1",
        preferred_term: "Weight loss",
        seeds: [
          { snomed_concept_id: "1", preferred_term: "Weight loss" },
          { snomed_concept_id: "2", preferred_term: "Nausea" },
        ],
      },
    });
    const spans = collectTreeHighlights(TEXT, tree);
    const words = spans.map((s) => TEXT.slice(s.start, s.end).toLowerCase());
    expect(words).toEqual(expect.arrayContaining(["weight loss", "nausea"]));
  });

  it("skips leaves with no verbatim wording (RULE_FIRED) without throwing", () => {
    const tree = makeNode({
      kind: "AND",
      children: [makeNode({ node_id: "n2", kind: "RULE_FIRED", referenced_rule_id: "r1" })],
    });
    expect(collectTreeHighlights(TEXT, tree)).toEqual([]);
  });

  it("returns an empty array when there is no recommendation text", () => {
    expect(collectTreeHighlights(null, makeNode({ kind: "DEMOGRAPHIC", field: "age" }))).toEqual(
      [],
    );
  });

  it("returns an empty array when there is no tree", () => {
    expect(collectTreeHighlights(TEXT, null)).toEqual([]);
  });
});
