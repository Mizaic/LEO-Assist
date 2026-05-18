import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import MultipleConsultationsSection from "../MultipleConsultationsSection";
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
  top_factors: [
    { factor: "different_initial_diagnosis", n: 12 },
    { factor: "co_morbidity_blurring", n: 8 },
  ],
  factors_by_cancer_type: {
    Breast: { different_initial_diagnosis: 5 },
    Colorectal: { different_initial_diagnosis: 7, co_morbidity_blurring: 8 },
  },
  episode_evidence: [
    {
      episode_id: "ep-test-001",
      cancer_type: "Breast",
      n: 3,
      factors: ["different_initial_diagnosis"],
      evidence_quotes: null,
    },
  ],
  llm_cost_usd: 0.4201,
  llm_input_tokens: 210000,
  llm_output_tokens: 35000,
  llm_calls: 48,
};

const sampleResult: AuditSectionResult<AuditConsultations> = {
  scopes: {
    practice: sampleData,
    alliance_live: null,
    england_live: null,
  },
  benchmark: null,
};

// Stub out per-year fetching so section renders without API.
const STUB_YEAR_STATES = [
  { year: 2024, loading: false, error: null, data: sampleData },
  { year: 2025, loading: false, error: null, data: sampleData },
];

jest.mock("@/components/audit/_useAuditYearWindows", () => ({
  useAuditYearWindows: () => ({ liveYears: STUB_YEAR_STATES }),
  BASELINE_YEAR: 2018,
}));
jest.mock("@/context/OrgContext", () => ({ useOrgId: () => undefined }));

describe("MultipleConsultationsSection", () => {
  it("renders section title", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    expect(screen.getByText(/reasons for multiple consultations/i)).toBeInTheDocument();
  });

  it("shows the top NCDA factor label for each live year card", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    // "different_initial_diagnosis" -> "Symptoms suggested different initial diagnosis"
    const labels = screen.getAllByText(/symptoms suggested different initial diagnosis/i);
    expect(labels.length).toBeGreaterThanOrEqual(1);
  });

  it("shows 'Top NCDA factor' sub-label on each year card", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    const subs = screen.getAllByText(/top ncda factor/i);
    expect(subs.length).toBeGreaterThanOrEqual(1);
  });

  it("opens the factors dialog when zoom button is clicked", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    const zoomBtns = screen.getAllByLabelText(/open \d+ multiple consultations/i);
    fireEvent.click(zoomBtns[0]);
    expect(screen.getByText(/factors by ncda category/i)).toBeInTheDocument();
  });

  it("shows NCDA category headings in the dialog", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    fireEvent.click(screen.getAllByLabelText(/open \d+ multiple consultations/i)[0]);
    expect(screen.getByText(/complexity of presentation/i)).toBeInTheDocument();
    expect(screen.getByText(/gp factors/i)).toBeInTheDocument();
  });

  it("shows LLM telemetry footer in the dialog", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    fireEvent.click(screen.getAllByLabelText(/open \d+ multiple consultations/i)[0]);
    expect(screen.getByText(/claude haiku/i)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.4201/)).toBeInTheDocument();
  });

  it("renders episode evidence accordion", () => {
    render(
      <MultipleConsultationsSection result={sampleResult} loading={false} />,
    );
    fireEvent.click(screen.getAllByLabelText(/open \d+ multiple consultations/i)[0]);
    expect(screen.getByText(/episode evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/breast/i)).toBeInTheDocument();
  });

  it("shows skeleton / loading state without error", () => {
    render(
      <MultipleConsultationsSection result={null} loading />,
    );
    // Should not show data content when loading
    expect(screen.queryByText(/factors by ncda category/i)).not.toBeInTheDocument();
  });
});
