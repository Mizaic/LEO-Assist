/**
 * Unit tests for leafTextMatch -- the shared "where does this leaf's
 * value live in the verbatim text?" helper used by both
 * StepPrerequisites (Step 1) and the wizard orchestrator (Step 3).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import {
  demographicMatchCandidate,
  leafTextMatch,
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

  it("anchors a CONCEPT leaf by its preferred_term", () => {
    const node = makeNode({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Weight loss" },
    });
    const match = leafTextMatch(TEXT, node);
    expect(match).not.toBeNull();
    expect(TEXT.slice(match!.start, match!.end).toLowerCase()).toBe("weight loss");
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
