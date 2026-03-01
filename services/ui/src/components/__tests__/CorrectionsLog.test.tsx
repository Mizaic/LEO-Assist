import React from "react";
import { render, screen } from "@testing-library/react";
import CorrectionsLog from "../CorrectionsLog";
import type { Correction } from "@/lib/types";

describe("CorrectionsLog", () => {
  it("shows empty message when no corrections", () => {
    render(<CorrectionsLog corrections={[]} />);
    expect(screen.getByText(/No corrections yet/)).toBeInTheDocument();
  });

  it("renders correction text and detail", () => {
    const corrections: Correction[] = [
      { type: "context", text: "Set negated", detail: "Changed flag", time: "2025-01-01T00:00:00Z" },
      { type: "add", text: "Added entity", detail: "Manual add", time: "2025-01-01T00:01:00Z" },
    ];
    render(<CorrectionsLog corrections={corrections} />);
    expect(screen.getByText("Set negated")).toBeInTheDocument();
    expect(screen.getByText("Changed flag")).toBeInTheDocument();
    expect(screen.getByText("Added entity")).toBeInTheDocument();
    expect(screen.getByText("Manual add")).toBeInTheDocument();
  });

  it("renders correct number of items", () => {
    const corrections: Correction[] = [
      { type: "context", text: "A", detail: "D1", time: "2025-01-01T00:00:00Z" },
      { type: "remove", text: "B", detail: "D2", time: "2025-01-01T00:01:00Z" },
      { type: "span", text: "C", detail: "D3", time: "2025-01-01T00:02:00Z" },
    ];
    render(<CorrectionsLog corrections={corrections} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });
});
