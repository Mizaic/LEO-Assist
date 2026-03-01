import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EntitySidebar from "../EntitySidebar";
import type { EncounterTerm } from "@/lib/types";

function makeTerm(overrides: Partial<EncounterTerm> = {}): EncounterTerm {
  return {
    term_id: "T1",
    text: "chest pain",
    span_start: 0,
    span_end: 10,
    context: { negated: false, uncertain: false, historical: false, subject: "patient", temporality: "present" },
    coding: { snomed_concept_id: "29857009", snomed_term: "Chest pain", score: 0.95 },
    evidence_text: "chest pain",
    extraction_method: "llm",
    extraction_confidence: 0.9,
    ...overrides,
  };
}

describe("EntitySidebar", () => {
  it("shows entity count in header", () => {
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} />);
    expect(screen.getByText(/Clinical Terms \(1\)/)).toBeInTheDocument();
  });

  it("renders entity text and SNOMED term", () => {
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} />);
    expect(screen.getByText("chest pain")).toBeInTheDocument();
    expect(screen.getByText("Chest pain")).toBeInTheDocument();
  });

  it("renders concept ID", () => {
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} />);
    expect(screen.getByText("29857009")).toBeInTheDocument();
  });

  it("shows confidence score as percentage", () => {
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} />);
    expect(screen.getByText("90%")).toBeInTheDocument();
  });

  it("calls onSelect when entity is clicked", async () => {
    const onSelect = jest.fn();
    const user = userEvent.setup();
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={onSelect} />);
    await user.click(screen.getByText("chest pain"));
    expect(onSelect).toHaveBeenCalledWith("T1");
  });

  it("shows NEG chip for negated terms", () => {
    render(
      <EntitySidebar
        terms={[makeTerm({ context: { negated: true, uncertain: false, historical: false, subject: "patient", temporality: "present" } })]}
        selectedId={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText("NEG")).toBeInTheDocument();
  });

  it("shows UNC chip for uncertain terms", () => {
    render(
      <EntitySidebar
        terms={[makeTerm({ context: { negated: false, uncertain: true, historical: false, subject: "patient", temporality: "present" } })]}
        selectedId={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText("UNC")).toBeInTheDocument();
  });

  it("shows remove button when onRemove is provided", async () => {
    const onRemove = jest.fn();
    const user = userEvent.setup();
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} onRemove={onRemove} />);
    const removeBtn = screen.getByTitle("Remove term");
    await user.click(removeBtn);
    expect(onRemove).toHaveBeenCalledWith("T1");
  });

  it("does not show remove button when onRemove is not provided", () => {
    render(<EntitySidebar terms={[makeTerm()]} selectedId={null} onSelect={jest.fn()} />);
    expect(screen.queryByTitle("Remove term")).not.toBeInTheDocument();
  });
});
