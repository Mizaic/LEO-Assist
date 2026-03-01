import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EntityCard from "../EntityCard";
import type { EncounterTerm } from "@/lib/types";

const term: EncounterTerm = {
  term_id: "T1",
  text: "chest pain",
  span_start: 0,
  span_end: 10,
  context: { negated: false, uncertain: false, historical: false, subject: "patient", temporality: "present" },
  coding: { snomed_concept_id: "29857009", snomed_term: "Chest pain", score: 0.95, read_code: "182.." },
  evidence_text: "chest pain",
  extraction_method: "llm",
  extraction_confidence: 0.92,
};

const defaults = {
  term,
  position: { top: 100, left: 200 },
  onClose: jest.fn(),
  onContextChange: jest.fn(),
  onReassign: jest.fn(),
  onAdjustSpan: jest.fn(),
  onRemove: jest.fn(),
  onCorrection: jest.fn(),
};

describe("EntityCard", () => {
  it("renders term text and extraction method", () => {
    render(<EntityCard {...defaults} />);
    expect(screen.getByText("chest pain")).toBeInTheDocument();
    expect(screen.getByText("llm")).toBeInTheDocument();
  });

  it("renders SNOMED concept ID and term", () => {
    render(<EntityCard {...defaults} />);
    expect(screen.getByText("29857009")).toBeInTheDocument();
    expect(screen.getByText("Chest pain")).toBeInTheDocument();
  });

  it("renders Read code", () => {
    render(<EntityCard {...defaults} />);
    expect(screen.getByText(/Read: 182/)).toBeInTheDocument();
  });

  it("renders confidence score", () => {
    render(<EntityCard {...defaults} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("renders context flag chips", () => {
    render(<EntityCard {...defaults} />);
    expect(screen.getByText("Neg")).toBeInTheDocument();
    expect(screen.getByText("Unc")).toBeInTheDocument();
    expect(screen.getByText("Hist")).toBeInTheDocument();
    expect(screen.getByText("Fam")).toBeInTheDocument();
  });

  it("calls onReassign when Reassign code button is clicked", async () => {
    const user = userEvent.setup();
    render(<EntityCard {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Reassign code" }));
    expect(defaults.onReassign).toHaveBeenCalledWith("T1");
  });

  it("calls onAdjustSpan when Adjust span button is clicked", async () => {
    const user = userEvent.setup();
    render(<EntityCard {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Adjust span" }));
    expect(defaults.onAdjustSpan).toHaveBeenCalledWith("T1");
  });

  it("calls onRemove and onCorrection when Remove entity is clicked", async () => {
    const user = userEvent.setup();
    render(<EntityCard {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Remove entity" }));
    expect(defaults.onRemove).toHaveBeenCalledWith("T1");
    expect(defaults.onCorrection).toHaveBeenCalledWith(
      expect.objectContaining({ type: "remove", text: "chest pain" }),
    );
  });

  it("toggling a context flag calls onContextChange", async () => {
    const user = userEvent.setup();
    render(<EntityCard {...defaults} />);
    await user.click(screen.getByText("Neg"));
    expect(defaults.onContextChange).toHaveBeenCalledWith(
      "T1",
      expect.objectContaining({ negated: true }),
    );
  });
});
