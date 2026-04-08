import React from "react";
import { render, screen } from "@testing-library/react";
import KPICards from "../KPICards";

const sampleKPIs = {
  avg_days_to_referral: 10.23,
  n_days_to_referral: 30,
  avg_days_to_diagnosis: 35.7,
  n_days_to_diagnosis: 35,
  avg_days_to_treatment: 25,
  n_days_to_treatment: 12,
  avg_consultations: 2.1,
  episode_count: 42,
};

describe("KPICards", () => {
  it("renders all 3 KPI rows", () => {
    render(<KPICards kpis={sampleKPIs} />);
    expect(screen.getByText(/First presentation to referral/)).toBeInTheDocument();
    expect(screen.getByText(/Referral to diagnosis/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnosis to treatment start/)).toBeInTheDocument();
    // avg_consultations is returned by the API but not displayed in KPICards
  });

  it("shows rounded values with units", () => {
    render(<KPICards kpis={sampleKPIs} />);
    expect(screen.getByText(/10.2/)).toBeInTheDocument();
    expect(screen.getByText(/35.7/)).toBeInTheDocument();
  });

  it("shows dash for null values", () => {
    render(
      <KPICards
        kpis={{ ...sampleKPIs, avg_days_to_referral: null }}
      />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows episode count", () => {
    render(<KPICards kpis={sampleKPIs} />);
    expect(screen.getByText(/Cohort size: 42 referral pathways/)).toBeInTheDocument();
  });

  it("shows empty message when kpis is null", () => {
    render(<KPICards kpis={null} />);
    expect(screen.getByText(/No waiting time data is available yet/)).toBeInTheDocument();
  });

  it("shows target values", () => {
    render(<KPICards kpis={sampleKPIs} />);
    expect(screen.getByText(/NHS target: 14 days/)).toBeInTheDocument();
    expect(screen.getByText(/NHS target: 28 days/)).toBeInTheDocument();
  });
});
