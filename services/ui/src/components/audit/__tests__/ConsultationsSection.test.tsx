import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import ConsultationsSection from "../ConsultationsSection";
import type { AuditConsultations, AuditSectionResult } from "@/lib/analyticsApi";

const sampleData: AuditConsultations = {
  three_or_more_pct: 35.3,
  three_or_more_n: 18,
  fewer_than_3_pct: 64.7,
  fewer_than_3_n: 33,
  total_episodes: 51,
  enriched_n: 48,
  enriched_pct: 94.1,
  median_consultations: 2,
  iqr_low: 1,
  iqr_high: 4,
  buckets: { "0": 3, "1": 10, "2": 6, "3-4": 14, "5-7": 10, "8+": 8 },
  buckets_pct: { "0": 5.9, "1": 19.6, "2": 11.8, "3-4": 27.5, "5-7": 19.6, "8+": 15.7 },
  mean_per_episode: {
    total: 3.2, f2f: 1.8, phone: 0.7, nurse: 0.3, email: 0.0,
    specialist_clinic: 0.2, home_visit: 0.1, phlebotomy: 0.1, result_review: 0.2,
  },
  total_consultations: 154,
  unrelated_filtered_total: 8,
  top_factors: [
    { factor: "different_initial_diagnosis", n: 12 },
    { factor: "co_morbidity_blurring", n: 8 },
  ],
  factors_by_cancer_type: {
    Breast: { different_initial_diagnosis: 5 },
    Colorectal: { different_initial_diagnosis: 7, co_morbidity_blurring: 8 },
  },
  episode_evidence: [],
  llm_cost_usd: 0.4201,
  llm_input_tokens: 210000,
  llm_output_tokens: 35000,
  llm_calls: 48,
};

const sampleResult: AuditSectionResult<AuditConsultations> = {
  scopes: {
    practice: sampleData,
    alliance_live: { ...sampleData, three_or_more_pct: 28.5, fewer_than_3_pct: 71.5 },
    england_live:  { ...sampleData, three_or_more_pct: 31.2, fewer_than_3_pct: 68.8 },
  },
  benchmark: {
    set_id: "bm-1",
    set_name: "Benchmark",
    metrics: {
      "consultations.three_or_more_pct":   { national: 31.2, alliance: 28.5 },
      "consultations.fewer_than_3_pct":    { national: 68.8, alliance: 71.5 },
      "consultations.median_consultations": { national: 1.5,  alliance: 1.4 },
    },
  },
};

jest.mock("@/components/audit/_useAuditYearWindows", () => ({
  useAuditYearWindows: () => ({ liveYears: [] }),
  BASELINE_YEAR: 2018,
}));
jest.mock("@/context/OrgContext", () => ({ useOrgId: () => undefined }));
jest.mock("@/context/AuditBenchmarkOverlayContext", () => ({
  useAuditBenchmarkOverlay: () => ({ showCancerAlliance: false, showAllPatients: false }),
}));

describe("ConsultationsSection", () => {
  it("renders section title", () => {
    render(<ConsultationsSection result={sampleResult} loading={false} />);
    expect(screen.getByText("Consultations")).toBeInTheDocument();
  });

  it("renders skeleton while loading and no data", () => {
    render(<ConsultationsSection result={null} loading />);
    expect(screen.getByText("Consultations")).toBeInTheDocument();
    expect(screen.queryByText(/31\.2%/)).not.toBeInTheDocument();
  });

  it("shows error alert when error is set", () => {
    render(<ConsultationsSection result={null} loading={false} error="Load failed" />);
    expect(screen.getByText("Load failed")).toBeInTheDocument();
  });

  it("shows the 2018 baseline derived from three_or_more_pct benchmark", () => {
    render(<ConsultationsSection result={sampleResult} loading={false} orgSelected />);
    // 2018 baseline card should show the national benchmark value
    expect(screen.getByText(/31\.2%/)).toBeInTheDocument();
  });
});
