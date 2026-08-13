/**
 * Plain-English copy helpers -- VT-LEO-AI-152 (health-literacy gate).
 *
 * The EditRuleDialog UI deliberately routes all user-facing wording through
 * `copy.ts` so QA can audit it in one place and so we can guarantee no
 * SNOMED / boolean-logic jargon leaks through to the reviewer.
 */

import {
  ADD_BAR_LABELS,
  DEMOGRAPHIC_FIELD_LABELS,
  GROUP_KIND_LABELS,
  GROUP_KIND_SHORT,
  OPERATOR_LABELS,
  STRENGTH_LABELS,
  friendlyTerm,
} from "../copy";

describe("EditRuleDialog/copy", () => {
  describe("friendlyTerm", () => {
    it.each([
      ["Cough (finding)", "Cough"],
      ["Acute appendicitis (disorder)", "Acute appendicitis"],
      ["History of asbestos exposure (situation)", "History of asbestos exposure"],
      ["Loss of appetite (finding)", "Loss of appetite"],
      ["Plain term with no suffix", "Plain term with no suffix"],
      ["", ""],
    ])("strips SNOMED semantic tag from %p", (raw, expected) => {
      expect(friendlyTerm(raw)).toBe(expected);
    });

    it("returns empty string for null / undefined", () => {
      expect(friendlyTerm(null)).toBe("");
      expect(friendlyTerm(undefined)).toBe("");
    });
  });

  describe("label maps", () => {
    it("exposes plain-English group labels for every supported kind", () => {
      expect(GROUP_KIND_LABELS.AND).toMatch(/ALL of these/);
      expect(GROUP_KIND_LABELS.OR).toMatch(/ANY of these/);
      expect(GROUP_KIND_LABELS.NOT).toMatch(/NOT have any of these/);
      expect(GROUP_KIND_SHORT.NOT).toMatch(/Should not have/);
      expect(GROUP_KIND_LABELS.AT_LEAST).toMatch(/at least N of these/);
      expect(GROUP_KIND_LABELS.MEDICATION).toMatch(/Medicine/);
      expect(GROUP_KIND_LABELS.ALLERGY).toMatch(/Allergy/);
      expect(GROUP_KIND_LABELS.TREATMENT_HISTORY).toMatch(/Past treatment/);
      expect(GROUP_KIND_LABELS.RULE_FIRED).toMatch(/another rule/);
      expect(Object.keys(GROUP_KIND_LABELS).sort()).toEqual(
        Object.keys(GROUP_KIND_SHORT).sort(),
      );
    });

    it("uses everyday words instead of technical jargon (health-literacy gate)", () => {
      const allCopy = [
        ...Object.values(GROUP_KIND_LABELS),
        ...Object.values(GROUP_KIND_SHORT),
        ...Object.values(DEMOGRAPHIC_FIELD_LABELS),
        ...Object.values(OPERATOR_LABELS),
        ...STRENGTH_LABELS.map((s) => s.label),
        ...Object.values(ADD_BAR_LABELS),
      ].join(" | ");
      expect(allCopy).not.toMatch(/SNOMED/i);
      expect(allCopy).not.toMatch(/criterion/i);
      expect(allCopy).not.toMatch(/\bdemographic\b/i);
      expect(allCopy).not.toMatch(/\boperator\b/i);
      expect(allCopy).not.toMatch(/AT_LEAST/);
    });

    it("translates demographic fields and operators into plain English", () => {
      expect(DEMOGRAPHIC_FIELD_LABELS.age).toBe("Patient's age");
      expect(DEMOGRAPHIC_FIELD_LABELS.sex).toBe("Patient's sex");
      expect(OPERATOR_LABELS[">="]).toBe("is at least");
      expect(OPERATOR_LABELS["<="]).toBe("is at most");
      expect(OPERATOR_LABELS[">"]).toBe("is more than");
      expect(OPERATOR_LABELS["<"]).toBe("is less than");
      expect(OPERATOR_LABELS["="]).toBe("is exactly");
    });

    it("provides a friendly label for every recommendation strength", () => {
      const values = STRENGTH_LABELS.map((s) => s.value);
      expect(values).toEqual(
        expect.arrayContaining([
          "offer",
          "consider",
          "refer",
          "safety_net",
          "do_not_offer",
          "unspecified",
        ])
      );
      const safetyNet = STRENGTH_LABELS.find((s) => s.value === "safety_net");
      expect(safetyNet?.label).toBe("Watch and check back");
    });
  });
});
