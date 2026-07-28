/**
 * Action group helpers -- preferred_fallback / any / AND.
 * Atlas: DI-42246DA7 / DO-F8C56339
 */
import {
  addFallbackAfter,
  addOrAlternativeAfter,
  formatActionGroupRecapLines,
  groupActionsForDisplay,
  removeActionKeepingGroups,
} from "../actionGroups";
import type { RuleAction } from "../types";

function coded(term: string, strength = "offer"): RuleAction {
  return {
    criterion: {
      snomed_concept_id: "1",
      preferred_term: term,
    },
    strength,
  };
}

describe("groupActionsForDisplay", () => {
  it("treats ungrouped rows as solo AND", () => {
    const actions = [coded("MRI"), coded("blood test")];
    const groups = groupActionsForDisplay(actions);
    expect(groups).toHaveLength(2);
    expect(groups[0]).toMatchObject({ mode: "all", indices: [0] });
    expect(groups[1]).toMatchObject({ mode: "all", indices: [1] });
  });

  it("collapses shared group_id into one display group", () => {
    const actions: RuleAction[] = [
      {
        ...coded("MRI"),
        group_id: "g1",
        group_mode: "preferred_fallback",
        group_rank: 0,
      },
      {
        ...coded("CT"),
        group_id: "g1",
        group_mode: "preferred_fallback",
        group_rank: 1,
      },
    ];
    const groups = groupActionsForDisplay(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].mode).toBe("preferred_fallback");
    expect(groups[0].indices).toEqual([0, 1]);
  });
});

describe("addFallbackAfter", () => {
  it("starts a preferred_fallback group with a blank second row", () => {
    const { actions, newIndex } = addFallbackAfter([coded("MRI")], 0);
    expect(actions).toHaveLength(2);
    expect(newIndex).toBe(1);
    expect(actions[0].group_mode).toBe("preferred_fallback");
    expect(actions[0].group_rank).toBe(0);
    expect(actions[1].group_id).toBe(actions[0].group_id);
    expect(actions[1].group_rank).toBe(1);
    expect(actions[1].criterion.snomed_concept_id).toBe("");
  });
});

describe("addOrAlternativeAfter", () => {
  it("starts an either/or group with a blank second row", () => {
    const { actions, newIndex } = addOrAlternativeAfter([coded("MRI")], 0);
    expect(newIndex).toBe(1);
    expect(actions[0].group_mode).toBe("any");
    expect(actions[1].group_mode).toBe("any");
    expect(actions[1].group_id).toBe(actions[0].group_id);
  });
});

describe("removeActionKeepingGroups", () => {
  it("dissolves a group when only one member remains", () => {
    const start: RuleAction[] = [
      {
        ...coded("MRI"),
        group_id: "g1",
        group_mode: "any",
        group_rank: 0,
      },
      {
        ...coded("CT"),
        group_id: "g1",
        group_mode: "any",
        group_rank: 1,
      },
    ];
    const next = removeActionKeepingGroups(start, 1);
    expect(next).toHaveLength(1);
    expect(next[0].group_id).toBeUndefined();
    expect(next[0].group_mode).toBeUndefined();
  });
});

describe("formatActionGroupRecapLines", () => {
  it("describes preferred then fallback in plain English", () => {
    const actions: RuleAction[] = [
      {
        ...coded("MRI of brain"),
        group_id: "g1",
        group_mode: "preferred_fallback",
        group_rank: 0,
      },
      {
        ...coded("CT of head"),
        group_id: "g1",
        group_mode: "preferred_fallback",
        group_rank: 1,
      },
    ];
    const lines = formatActionGroupRecapLines(actions);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain("If this rule matches:");
    expect(lines[0]).toContain("If that is not available:");
    expect(lines[0]).toContain("MRI");
    expect(lines[0]).toContain("CT");
  });
});
