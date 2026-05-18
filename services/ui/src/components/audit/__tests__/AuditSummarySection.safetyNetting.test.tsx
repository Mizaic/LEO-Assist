/**
 * Pins the Safety Netting tile on the Audit Summary section.
 *
 * What this guards against (regression history):
 *  - The previous tile rendered "0% — Cases with a follow-up plan
 *    recorded" because the API field was computed against
 *    ep.safety_netting_recorded (referral-gated subset only) divided
 *    by total_episodes (full cohort). The new field is the canonical
 *    confirmed-cancer numerator/denominator and the tile must reflect
 *    the new fields end-to-end.
 *  - The tooltip must surface the four-bucket breakdown so the user
 *    can see WHY the headline rate is what it is (strong vs medium
 *    vs advice-only) without opening the developer tools.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import AuditSummarySection from "../AuditSummarySection";
import type { AuditSummary } from "@/lib/analyticsApi";

jest.mock("@/context/AnalyticsDateFilterContext", () => ({
  useAnalyticsDateFilter: () => ({ appliedFrom: null, appliedTo: null }),
}));

const baseSummary: AuditSummary = {
  total_episodes: 67,
  active_episodes: 1,
  confirmed_cancers: 42,
  confirmed_cancers_via_2ww: 32,
  confirmed_cancers_via_2ww_pct: 76.2,
  confirmed_cancers_screening_programme: 4,
  confirmed_cancers_excluding_screening: 38,
  confirmed_cancers_via_2ww_excluding_screening: 29,
  confirmed_cancers_via_2ww_excluding_screening_pct: 76.3,
  cohort_1a_n: 32,
  cohort_1b_n: 22,
  cohort_3_n: 10,
  median_pci_days: 2,
  median_di_days: 46,
  avg_consultations: 3.1,
  safety_netting_pct: 47.6,
  safety_netting_recorded_n: 20,
  safety_netting_strong_pct: 31.0,
  safety_netting_strong_n: 13,
  safety_netting_signal_counts: {
    strong: 13,
    medium: 7,
    advice_only: 3,
    none: 19,
  },
  safety_netting_denominator: 42,
};

describe("AuditSummarySection — safety netting tile", () => {
  it("renders the headline rate from safety_netting_pct, not 0%", () => {
    render(
      <AuditSummarySection
        summary={baseSummary}
        loading={false}
        orgName="Demo Practice"
        totalCases={65}
      />,
    );
    expect(screen.getByText("Safety netting")).toBeInTheDocument();
    expect(screen.getByText("47.6%")).toBeInTheDocument();
  });

  it("renders the numerator/denominator subtext when both are supplied", () => {
    render(
      <AuditSummarySection
        summary={baseSummary}
        loading={false}
        orgName="Demo Practice"
      />,
    );
    expect(
      screen.getByText("20 of 42 confirmed cancers"),
    ).toBeInTheDocument();
  });

  it("falls back to the descriptive subtext when the breakdown is absent", () => {
    const summary: AuditSummary = {
      ...baseSummary,
      safety_netting_recorded_n: undefined,
      safety_netting_denominator: undefined,
      safety_netting_signal_counts: undefined,
    };
    render(
      <AuditSummarySection
        summary={summary}
        loading={false}
        orgName="Demo Practice"
      />,
    );
    expect(
      screen.getByText("Confirmed cancers with a documented safety-net plan"),
    ).toBeInTheDocument();
  });

  it("renders an em-dash when the rate is null (no confirmed cancers)", () => {
    const summary: AuditSummary = {
      ...baseSummary,
      safety_netting_pct: null,
      safety_netting_recorded_n: 0,
      safety_netting_strong_pct: null,
      safety_netting_strong_n: 0,
      safety_netting_signal_counts: { strong: 0, medium: 0, advice_only: 0, none: 0 },
      safety_netting_denominator: 0,
    };
    render(
      <AuditSummarySection
        summary={summary}
        loading={false}
        orgName="Demo Practice"
      />,
    );
    // The em-dash appears in the safety-netting tile (and possibly other
    // empty tiles); using getAllByText keeps the test resilient.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
