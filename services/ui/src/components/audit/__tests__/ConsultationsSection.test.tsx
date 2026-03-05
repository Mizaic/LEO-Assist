import React from "react";
import { render, screen } from "@testing-library/react";
import ConsultationsSection from "../ConsultationsSection";
import type { AuditConsultations } from "@/lib/analyticsApi";

const sampleData: AuditConsultations = {
  fewer_than_3_pct: 82.4,
  three_or_more_pct: 17.6,
  fewer_than_3_n: 42,
  three_or_more_n: 9,
  total_episodes: 51,
  median_consultations: 1,
  iqr_low: 1,
  iqr_high: 2,
};

describe("ConsultationsSection", () => {
  it("renders section title", () => {
    render(<ConsultationsSection data={sampleData} loading={false} />);
    expect(screen.getByText("Consultations")).toBeInTheDocument();
  });

  it("renders skeleton while loading", () => {
    render(<ConsultationsSection data={null} loading />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders chart when data is available", () => {
    render(<ConsultationsSection data={sampleData} loading={false} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("shows error alert when error is set", () => {
    render(<ConsultationsSection data={null} loading={false} error="Load failed" />);
    expect(screen.getByText("Load failed")).toBeInTheDocument();
  });

  it("shows national and alliance benchmark in summary table", () => {
    render(<ConsultationsSection data={sampleData} loading={false} />);
    expect(screen.getByText("71.5")).toBeInTheDocument();
    expect(screen.getByText("68.8")).toBeInTheDocument();
  });
});
