/**
 * Normalise flat API action payloads into nested RuleAction shape.
 * Guards against the EditRuleDialog crash when actions[] items lack
 * a ``criterion`` wrapper (DI-42246DA7).
 */
import {
  normalizeRuleAction,
  normalizeRuleActions,
} from "../actionShape";

describe("normalizeRuleAction", () => {
  it("wraps a flat API item into nested criterion + strength", () => {
    const flat = {
      snomed_concept_id: "168731009",
      preferred_term: "Plain chest X-ray (procedure)",
      semantic_tag: "procedure",
      term: "chest X-ray",
      strength: "offer",
    };
    expect(normalizeRuleAction(flat)).toEqual({
      criterion: {
        snomed_concept_id: "168731009",
        preferred_term: "Plain chest X-ray (procedure)",
        semantic_tag: "procedure",
        term: "chest X-ray",
      },
      strength: "offer",
    });
  });

  it("passes through an already-nested RuleAction unchanged", () => {
    const nested = {
      criterion: {
        snomed_concept_id: "166717003",
        preferred_term: "Full blood count",
        semantic_tag: "procedure",
      },
      strength: "consider",
    };
    expect(normalizeRuleAction(nested)).toEqual(nested);
  });

  it("keeps preferred_fallback group fields from a flat API item", () => {
    const flat = {
      snomed_concept_id: "113091000",
      preferred_term: "Magnetic resonance imaging",
      strength: "offer",
      group_id: "ag_mri_ct",
      group_mode: "preferred_fallback",
      group_rank: 0,
    };
    expect(normalizeRuleAction(flat)).toMatchObject({
      criterion: { snomed_concept_id: "113091000" },
      strength: "offer",
      group_id: "ag_mri_ct",
      group_mode: "preferred_fallback",
      group_rank: 0,
    });
  });

  it("returns a blank row for null or non-object input", () => {
    expect(normalizeRuleAction(null)).toEqual({
      criterion: { snomed_concept_id: "", preferred_term: "" },
      strength: "unspecified",
    });
  });
});

describe("normalizeRuleActions", () => {
  it("maps each flat item in an array", () => {
    const flatList = [
      {
        snomed_concept_id: "168731009",
        preferred_term: "Plain chest X-ray (procedure)",
        strength: "offer",
      },
      {
        snomed_concept_id: "166717003",
        preferred_term: "Full blood count",
        strength: "consider",
      },
    ];
    const out = normalizeRuleActions(flatList);
    expect(out).toHaveLength(2);
    expect(out![0].criterion.snomed_concept_id).toBe("168731009");
    expect(out![0].strength).toBe("offer");
    expect(out![1].criterion.snomed_concept_id).toBe("166717003");
    expect(out![1].strength).toBe("consider");
  });

  it("returns undefined when input is absent", () => {
    expect(normalizeRuleActions(undefined)).toBeUndefined();
  });
});
