import React from "react";
import { render, screen } from "@testing-library/react";
import CancerTypeSection from "../CancerTypeSection";
import type { AuditCancerTypeRow } from "@/lib/analyticsApi";

const sampleData: AuditCancerTypeRow[] = [
  { cancer_type: "Breast", n: 14, pct: 27.5 },
  { cancer_type: "Colorectal", n: 8, pct: 15.7 },
  { cancer_type: "Lung", n: 8, pct: 15.7 },
  { cancer_type: "Prostate", n: 4, pct: 7.8 },
];

describe("CancerTypeSection", () => {
  it("renders section title", () => {
    render(<CancerTypeSection data={sampleData} loading={false} />);
    expect(screen.getByText("Cancer Type")).toBeInTheDocument();
  });

  it("renders chart with data", () => {
    render(<CancerTypeSection data={sampleData} loading={false} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("shows empty state when no data", () => {
    render(<CancerTypeSection data={[]} loading={false} />);
    expect(screen.getByText(/No cancer type data/)).toBeInTheDocument();
  });

  it("renders national benchmarks in table", () => {
    render(<CancerTypeSection data={sampleData} loading={false} />);
    expect(screen.getByText("27.5")).toBeInTheDocument();
    expect(screen.getByText("15.3")).toBeInTheDocument();
  });
});
