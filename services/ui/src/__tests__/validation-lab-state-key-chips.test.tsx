/**
 * VT: present pipeline keys show green with a value tooltip.
 *
 * Atlas: DI-FE423B8D / DO-158BE606 / VT-C9851641
 */
import { render, screen } from "@testing-library/react";

import { StateKeyChips } from "../app/admin/validation-lab/inspector/StateKeyChips";
import {
  TOOLTIP_MAX,
  formatKeyTooltip,
  isPresentValue,
} from "../app/admin/validation-lab/inspector/stateKeyPresence";

describe("stateKeyPresence", () => {
  it("treats non-empty strings, numbers, and booleans as present", () => {
    expect(isPresentValue("dysphagia")).toBe(true);
    expect(isPresentValue(0)).toBe(true);
    expect(isPresentValue(false)).toBe(true);
  });

  it("treats empty strings, null, empty arrays, and empty objects as absent", () => {
    expect(isPresentValue("")).toBe(false);
    expect(isPresentValue("  ")).toBe(false);
    expect(isPresentValue(null)).toBe(false);
    expect(isPresentValue(undefined)).toBe(false);
    expect(isPresentValue([])).toBe(false);
    expect(isPresentValue({})).toBe(false);
  });

  it("shows stored content in the tooltip when the value is present", () => {
    expect(formatKeyTooltip("hello", true)).toBe("hello");
    expect(formatKeyTooltip({ id: "1" }, true)).toContain("1");
  });

  it("lists facts and SNOMED codes in the entities tooltip", () => {
    const text = formatKeyTooltip(
      [{ text: "dysphagia", concept_id: "40739000" }],
      true,
    );
    expect(text).toContain("dysphagia");
    expect(text).toContain("40739000");
  });

  it("shows DOCUMENTS evidence span and evidence_sentence in the tooltip", () => {
    const text = formatKeyTooltip(
      [
        {
          text: "dysphagia",
          concept_id: "40739000",
          evidence: "dysphagia",
          evidence_sentence: "Reports progressive dysphagia for 6 weeks.",
        },
      ],
      true,
    );
    expect(text).toContain("evidence: dysphagia");
    expect(text).toContain(
      "evidence_sentence: Reports progressive dysphagia for 6 weeks.",
    );
  });

  it("resolves evidence_sentence from sibling sentences via __sentence_id", () => {
    const text = formatKeyTooltip(
      [{ text: "dysphagia", concept_id: "40739000", __sentence_id: "s-1" }],
      true,
      [{ sentence_id: "s-1", text: "Reports progressive dysphagia for 6 weeks." }],
    );
    expect(text).toContain("evidence: dysphagia");
    expect(text).toContain(
      "evidence_sentence: Reports progressive dysphagia for 6 weeks.",
    );
  });

  it("explains empty and not-yet-loaded keys", () => {
    expect(formatKeyTooltip(null, false)).toBe("Value not loaded yet");
    expect(formatKeyTooltip("", true)).toBe("No value");
  });

  it("keeps long stored values intact past 8000 characters", () => {
    const description = "Denial of fever. ".repeat(600);
    const text = formatKeyTooltip(
      { description, category: "assertion:absent" },
      true,
    );
    expect(text.length).toBeGreaterThan(8000);
    expect(text).toContain("assertion:absent");
    expect(text).not.toMatch(/\.\.\.$/);
  });

  it("adds a remainder note only after the high character cap", () => {
    const huge = "x".repeat(TOOLTIP_MAX + 40);
    const text = formatKeyTooltip(huge, true);
    expect(text).toContain("truncated, 40 more characters");
    expect(text.startsWith("x".repeat(80))).toBe(true);
  });
});

describe("StateKeyChips", () => {
  it("marks filled keys present and empty keys outlined", () => {
    render(
      <StateKeyChips
        keys={["patient_id", "errors"]}
        values={{ patient_id: "abc", errors: [] }}
        valuesReady
      />,
    );
    expect(screen.getByLabelText("patient_id: has a value")).toHaveAttribute(
      "data-present",
      "true",
    );
    expect(screen.getByLabelText("errors: empty")).toHaveAttribute(
      "data-present",
      "false",
    );
  });

  it("expands entity arrays into fact and code chips", () => {
    render(
      <StateKeyChips
        keys={["entities"]}
        values={{
          entities: [{ text: "dysphagia", concept_id: "40739000" }],
        }}
        valuesReady
      />,
    );
    expect(screen.getByTestId("validation-lab-entity-chip")).toHaveTextContent(
      "dysphagia -- 40739000",
    );
  });

  it("does not expand letter sentences as fact chips", () => {
    render(
      <StateKeyChips
        keys={["sentences"]}
        values={{
          sentences: [{ text: "Presenting complaint: Jaundice and weight loss." }],
        }}
        valuesReady
      />,
    );
    expect(screen.queryByTestId("validation-lab-entity-chip")).toBeNull();
    expect(screen.getByLabelText("sentences: has a value")).toHaveAttribute(
      "data-present",
      "true",
    );
  });
});
