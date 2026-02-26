import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpanAdjustBanner from "../SpanAdjustBanner";
import type { EncounterTerm } from "@/lib/types";

const term: EncounterTerm = {
  term_id: "T1",
  text: "chest",
  span_start: 5,
  span_end: 10,
  context: { negated: false, uncertain: false, historical: false, subject: "patient", temporality: "present" },
  coding: { snomed_concept_id: "29857009" },
  evidence_text: "chest",
  extraction_method: "llm",
};

const fullText = "The chest pain is severe and constant";

describe("SpanAdjustBanner", () => {
  const defaults = {
    term,
    fullText,
    onSave: jest.fn(),
    onCancel: jest.fn(),
    onCorrection: jest.fn(),
  };

  it("renders term text and start/end fields", () => {
    render(<SpanAdjustBanner {...defaults} />);
    expect(screen.getByText(/chest/)).toBeInTheDocument();
    expect(screen.getByLabelText("Start")).toBeInTheDocument();
    expect(screen.getByLabelText("End")).toBeInTheDocument();
  });

  it("shows preview text from span", () => {
    render(<SpanAdjustBanner {...defaults} />);
    expect(screen.getByText(/chest/)).toBeInTheDocument();
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    render(<SpanAdjustBanner {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(defaults.onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onSave when Save is clicked", async () => {
    const user = userEvent.setup();
    render(<SpanAdjustBanner {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(defaults.onSave).toHaveBeenCalledWith("T1", 5, 10, expect.any(String));
  });
});
