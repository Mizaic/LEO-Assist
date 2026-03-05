import React from "react";
import { render, screen } from "@testing-library/react";
import CancerTypeSection from "../CancerTypeSection";
import type { AuditCancerTypeRow, AuditSectionResult } from "@/lib/analyticsApi";

const sampleRows: AuditCancerTypeRow[] = [
  { cancer_type: "breast", n: 14, pct: 27.5 },
  { cancer_type: "colorectal", n: 8, pct: 15.7 },
  { cancer_type: "lung", n: 8, pct: 15.7 },
];

const sampleResult: AuditSectionResult<AuditCancerTypeRow[]> = {
  scopes: {
    practice: sampleRows,
    alliance_live: null,
    england_live: null,
  },
  benchmark: null,
};

describe("CancerTypeSection", () => {
  it("renders section title", () => {
    render(<CancerTypeSection result={sampleResult} loading={false} />);
    expect(screen.getByText("Cancer Type")).toBeInTheDocument();
  });

  it("shows empty state when practice data is empty", () => {
    const emptyResult: AuditSectionResult<AuditCancerTypeRow[]> = {
      scopes: { practice: [], alliance_live: null, england_live: null },
      benchmark: null,
    };
    render(<CancerTypeSection result={emptyResult} loading={false} />);
    expect(screen.getByText(/No cancer type data/i)).toBeInTheDocument();
  });

  it("shows empty state when result is null", () => {
    render(<CancerTypeSection result={null} loading={false} />);
    expect(screen.getByText(/No cancer type data/i)).toBeInTheDocument();
  });

  it("does not render content while loading", () => {
    render(<CancerTypeSection result={null} loading={true} />);
    // When loading, SectionCard renders a Skeleton – children (inc. empty state) are suppressed
    expect(screen.queryByText(/No cancer type data/i)).not.toBeInTheDocument();
  });

  it("renders practice data values in the table", () => {
    render(<CancerTypeSection result={sampleResult} loading={false} />);
    // breast cancer_type should appear in the table
    const breastCells = screen.getAllByText(/breast/i);
    expect(breastCells.length).toBeGreaterThan(0);
  });
});
