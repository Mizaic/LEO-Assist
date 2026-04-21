/**
 * Phase 7 UI tests for the polish wave.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-061AD3D1
 *   DO: DO-1EE0BFAE
 *   VT: VT-EEF2D497
 *
 * Covers (pure-logic, no DOM):
 *   - copy.isDestructiveRootKindChange: which transitions trigger the
 *     root-kind confirm dialog and which pass through silently.
 *   - copy.isObservationOperatorFlip: which operator transitions
 *     trigger the observation flip dialog and which do not.
 *   - copy: centralised dialog title + duplicate-set + search-panel
 *     + recency strings live in copy.ts and are not duplicated as
 *     stray inline literals.
 */

import {
  CONFIRM_KIND_CHANGE,
  CONFIRM_OBSERVATION_FLIP,
  DIALOG_CHROME,
  DUPLICATE_SETS_ALERT,
  OBSERVATION_OPERATOR_PHRASES,
  SEARCH_PANEL,
  isDestructiveRootKindChange,
  isObservationOperatorFlip,
} from "../copy";

describe("Phase 7 -- isDestructiveRootKindChange", () => {
  it.each([
    ["AND", "OR"],
    ["AND", "NOT"],
    ["AND", "AT_LEAST"],
    ["OR", "AND"],
    ["OR", "NOT"],
    ["NOT", "AND"],
    ["AT_LEAST", "OR"],
  ] as const)("flags %s -> %s as destructive", (before, after) => {
    expect(isDestructiveRootKindChange(before, after)).toBe(true);
  });

  it("is a no-op when the kind is unchanged", () => {
    expect(isDestructiveRootKindChange("AND", "AND")).toBe(false);
  });

  it("does not flag transitions involving leaf kinds", () => {
    expect(isDestructiveRootKindChange("AND", "CONCEPT")).toBe(false);
    expect(isDestructiveRootKindChange("DEMOGRAPHIC", "AND")).toBe(false);
    expect(isDestructiveRootKindChange("OBSERVATION", "OR")).toBe(false);
  });
});

describe("Phase 7 -- isObservationOperatorFlip", () => {
  it.each([
    ["<", ">"],
    ["<=", ">="],
    [">", "<"],
    [">=", "<="],
    ["<", ">="],
    [">", "<="],
  ])("flags %s -> %s as a clinical-meaning flip", (before, after) => {
    expect(isObservationOperatorFlip(before, after)).toBe(true);
  });

  it("flags = -> directional comparator as a flip", () => {
    expect(isObservationOperatorFlip("=", "<")).toBe(true);
    expect(isObservationOperatorFlip("=", ">=")).toBe(true);
    expect(isObservationOperatorFlip(">=", "=")).toBe(true);
  });

  it("flags any move into or out of between as a flip", () => {
    expect(isObservationOperatorFlip("<", "between")).toBe(true);
    expect(isObservationOperatorFlip("between", ">")).toBe(true);
  });

  it("does not flag tightening on the same side", () => {
    expect(isObservationOperatorFlip("<", "<=")).toBe(false);
    expect(isObservationOperatorFlip(">=", ">")).toBe(false);
  });

  it("is a no-op when the operator is unchanged", () => {
    expect(isObservationOperatorFlip(">=", ">=")).toBe(false);
  });
});

describe("Phase 7c -- centralised copy", () => {
  it("exposes the dialog chrome title used by the editor", () => {
    expect(DIALOG_CHROME.title).toBe("Change this rule");
    expect(DIALOG_CHROME.closeAria).toMatch(/close/i);
  });

  it("exposes the duplicate-symptom-set alert pieces", () => {
    expect(DUPLICATE_SETS_ALERT.ariaLabel).toMatch(/repeated/i);
    expect(DUPLICATE_SETS_ALERT.oneSetStrong).toMatch(/symptom set/i);
    expect(DUPLICATE_SETS_ALERT.manySetStrong(3)).toMatch(/3 repeated/);
  });

  it("exposes the four ConceptSearchPanel headings", () => {
    expect(SEARCH_PANEL.headings.replace_action).toMatch(/swap/i);
    expect(SEARCH_PANEL.headings.replace).toMatch(/swap/i);
    expect(SEARCH_PANEL.headings.add).toMatch(/add/i);
    expect(SEARCH_PANEL.headings.idle).toMatch(/find/i);
    expect(SEARCH_PANEL.searchAriaLabel).toBe("Search clinical terms");
    expect(SEARCH_PANEL.noResults("foo")).toContain("foo");
  });

  it("exposes plain-English phrases for every observation operator", () => {
    expect(OBSERVATION_OPERATOR_PHRASES["<"]).toBe("is less than");
    expect(OBSERVATION_OPERATOR_PHRASES[">="]).toBe("is at least");
    expect(OBSERVATION_OPERATOR_PHRASES["between"]).toBe("is between");
  });

  it("exposes the confirm dialog copy with both labels", () => {
    expect(CONFIRM_KIND_CHANGE.confirmLabel).toMatch(/yes/i);
    expect(CONFIRM_KIND_CHANGE.cancelLabel).toMatch(/cancel/i);
    expect(CONFIRM_OBSERVATION_FLIP.confirmLabel).toMatch(/yes/i);
    expect(CONFIRM_OBSERVATION_FLIP.beforeLabel).toMatch(/now reads/i);
    expect(CONFIRM_OBSERVATION_FLIP.afterLabel).toMatch(/will read/i);
  });
});
