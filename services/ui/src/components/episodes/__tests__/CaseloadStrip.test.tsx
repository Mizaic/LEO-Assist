import React from "react";
import { render, screen } from "@testing-library/react";
import CaseloadStrip from "../CaseloadStrip";
import type { CaseloadSummary } from "@/lib/pathwayRisk";

const summary: CaseloadSummary = {
  total: 25,
  onTrack: 15,
  atRisk: 5,
  breached: 3,
  completed: 2,
  unknown: 0,
};

describe("CaseloadStrip", () => {
  it("renders all four segment counts", () => {
    render(<CaseloadStrip summary={summary} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders segment labels", () => {
    render(<CaseloadStrip summary={summary} />);
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("At risk")).toBeInTheDocument();
    expect(screen.getByText("On track")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders with zero counts", () => {
    const empty: CaseloadSummary = {
      total: 0,
      onTrack: 0,
      atRisk: 0,
      breached: 0,
      completed: 0,
      unknown: 0,
    };
    render(<CaseloadStrip summary={empty} />);
    expect(screen.getAllByText("0")).toHaveLength(4);
  });
});
