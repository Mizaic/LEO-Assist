import React from "react";
import { render, screen } from "@testing-library/react";
import ConsultationsSection from "../ConsultationsSection";
import type { AuditConsultations, AuditSectionResult } from "@/lib/analyticsApi";

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

const sampleResult: AuditSectionResult<AuditConsultations> = {
  scopes: {
    practice: sampleData,
    alliance_live: { ...sampleData, fewer_than_3_pct: 71.5, three_or_more_pct: 28.5 },
    england_live: { ...sampleData, fewer_than_3_pct: 68.8, three_or_more_pct: 31.2 },
  },
  benchmark: {
    set_id: "bm-1",
    set_name: "Benchmark",
    metrics: {
      "consultations.fewer_than_3_pct": { national: 68.8, alliance: 71.5 },
      "consultations.median_consultations": { national: 1.5, alliance: 1.4 },
    },
  },
};

describe("ConsultationsSection", () => {
  it("renders section title", () => {
    render(<ConsultationsSection result={sampleResult} loading={false} />);
    expect(screen.getByText("Consultations")).toBeInTheDocument();
  });

  it("renders skeleton while loading", () => {
    render(<ConsultationsSection result={null} loading />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders chart when data is available", () => {
    render(<ConsultationsSection result={sampleResult} loading={false} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("shows error alert when error is set", () => {
    render(<ConsultationsSection result={null} loading={false} error="Load failed" />);
    expect(screen.getByText("Load failed")).toBeInTheDocument();
  });

  it("shows national and alliance benchmark in summary table", () => {
    render(<ConsultationsSection result={sampleResult} loading={false} />);
    expect(screen.getByText((content) => content.includes("68.8"))).toBeInTheDocument();
  });
});
