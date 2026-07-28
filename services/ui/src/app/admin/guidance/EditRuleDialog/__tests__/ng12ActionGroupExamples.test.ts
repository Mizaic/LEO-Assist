/**
 * NG12 examples for preferred-then-fallback and either/or procedure
 * groups (ease-of-use action shapes).
 *
 *   1.2.5 -- CT, or ultrasound if CT not available (pancreas)
 *   1.9.1 -- MRI brain, or CT if MRI contraindicated
 *   1.10.4 -- PV or ESR; serum FLC, or Bence-Jones if FLC not available
 *
 * Atlas: DI-42246DA7 / DO-F8C56339
 */
import { normalizeRuleActions } from "../../actionShape";
import {
  formatActionGroupRecapLines,
  groupActionsForDisplay,
} from "../actionGroups";
import { sanitiseActionsForSave } from "../treeOps";
import type { RuleAction } from "../types";

function action(
  id: string,
  term: string,
  strength: string,
  group?: {
    group_id: string;
    group_mode: "any" | "preferred_fallback";
    group_rank: number;
  },
): RuleAction {
  return {
    criterion: {
      snomed_concept_id: id,
      preferred_term: term,
      semantic_tag: "procedure",
    },
    strength,
    ...group,
  };
}

describe("NG12 1.2.5 -- CT then ultrasound if CT not available", () => {
  const actions: RuleAction[] = [
    action("419394006", "CT of abdomen and pelvis", "consider", {
      group_id: "ng12-1-2-5",
      group_mode: "preferred_fallback",
      group_rank: 0,
    }),
    action("418394000", "Ultrasound scan of abdomen", "consider", {
      group_id: "ng12-1-2-5",
      group_mode: "preferred_fallback",
      group_rank: 1,
    }),
  ];

  it("groups as one preferred_fallback display group", () => {
    const groups = groupActionsForDisplay(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].mode).toBe("preferred_fallback");
    expect(groups[0].indices).toEqual([0, 1]);
  });

  it("recaps CT first, then ultrasound if not available", () => {
    const line = formatActionGroupRecapLines(actions)[0];
    expect(line).toMatch(/If this rule matches:.*CT of abdomen/i);
    expect(line).toMatch(/If that is not available:.*Ultrasound scan of abdomen/i);
  });

  it("round-trips through sanitise + normalize with group fields", () => {
    const saved = sanitiseActionsForSave(actions);
    expect(saved[0]).toMatchObject({
      group_id: "ng12-1-2-5",
      group_mode: "preferred_fallback",
      group_rank: 0,
    });
    expect(saved[1]).toMatchObject({
      group_id: "ng12-1-2-5",
      group_mode: "preferred_fallback",
      group_rank: 1,
    });
    const loaded = normalizeRuleActions(saved);
    expect(loaded).toEqual(actions);
  });
});

describe("NG12 1.9.1 -- MRI brain, or CT if MRI contraindicated", () => {
  const actions: RuleAction[] = [
    action("816077007", "MRI of brain", "consider", {
      group_id: "ng12-1-9-1",
      group_mode: "preferred_fallback",
      group_rank: 0,
    }),
    action("303653007", "CT of head", "consider", {
      group_id: "ng12-1-9-1",
      group_mode: "preferred_fallback",
      group_rank: 1,
    }),
  ];

  it("groups MRI then CT as preferred_fallback", () => {
    const groups = groupActionsForDisplay(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].mode).toBe("preferred_fallback");
  });

  it("recap names MRI first and CT as the fallback", () => {
    const line = formatActionGroupRecapLines(actions)[0];
    expect(line).toMatch(/If this rule matches:.*MRI of brain/i);
    expect(line).toMatch(/If that is not available:.*CT of head/i);
  });

  it("preserves group fields on save", () => {
    const saved = sanitiseActionsForSave(actions);
    expect(saved.map((a) => a.group_mode)).toEqual([
      "preferred_fallback",
      "preferred_fallback",
    ]);
    expect(normalizeRuleActions(saved)).toEqual(actions);
  });
});

describe("NG12 1.10.4 -- myeloma bloods with OR and FLC fallback", () => {
  const actions: RuleAction[] = [
    action("26604007", "Full blood count", "offer"),
    action("718", "Serum calcium measurement", "offer"),
    action("365616007", "Plasma viscosity measurement", "offer", {
      group_id: "ng12-1-10-4-pv-esr",
      group_mode: "any",
      group_rank: 0,
    }),
    action("416125006", "Erythrocyte sedimentation rate", "offer", {
      group_id: "ng12-1-10-4-pv-esr",
      group_mode: "any",
      group_rank: 1,
    }),
    action("313500009", "Serum protein electrophoresis", "offer"),
    action("104435004", "Serum free light chain assay", "offer", {
      group_id: "ng12-1-10-4-flc",
      group_mode: "preferred_fallback",
      group_rank: 0,
    }),
    action("252378009", "Bence-Jones protein urine test", "offer", {
      group_id: "ng12-1-10-4-flc",
      group_mode: "preferred_fallback",
      group_rank: 1,
    }),
  ];

  it("keeps AND singles separate from the any and fallback groups", () => {
    const groups = groupActionsForDisplay(actions);
    expect(groups.map((g) => g.mode)).toEqual([
      "all",
      "all",
      "any",
      "all",
      "preferred_fallback",
    ]);
    expect(groups.find((g) => g.mode === "any")?.indices).toHaveLength(2);
    expect(
      groups.find((g) => g.mode === "preferred_fallback")?.indices,
    ).toHaveLength(2);
  });

  it("recaps either/or for PV/ESR and fallback for FLC/Bence-Jones", () => {
    const lines = formatActionGroupRecapLines(actions);
    const anyLine = lines.find((l) => l.includes(", or "));
    expect(anyLine).toMatch(/Plasma viscosity/i);
    expect(anyLine).toMatch(/Erythrocyte sedimentation rate/i);
    const fallback = lines.find((l) => l.includes("If that is not available"));
    expect(fallback).toMatch(/Serum free light chain/i);
    expect(fallback).toMatch(/Bence-Jones/i);
  });

  it("round-trips the mixed group payload", () => {
    const saved = sanitiseActionsForSave(actions);
    expect(saved.filter((a) => a.group_mode === "any")).toHaveLength(2);
    expect(
      saved.filter((a) => a.group_mode === "preferred_fallback"),
    ).toHaveLength(2);
    expect(saved.filter((a) => !a.group_id)).toHaveLength(3);
    expect(normalizeRuleActions(saved)).toEqual(actions);
  });
});
