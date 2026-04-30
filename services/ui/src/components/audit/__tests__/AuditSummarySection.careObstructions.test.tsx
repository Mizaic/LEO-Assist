/**
 * Pins the Care Obstructions tile on the Audit Summary section.
 *
 * What this guards against:
 *  - Headline rate must come from `care_obstruction_pct` (not the
 *    severe-only subset).
 *  - Numerator / denominator subtext must read "X of Y confirmed
 *    cancers" so the user knows the comparator without opening a
 *    dialog.
 *  - Tooltip must surface the four-bucket signal breakdown
 *    (rejection / DNA / cancellation / access barrier) to explain
 *    WHERE the headline rate comes from — mirroring the safety-
 *    netting tile pattern.
 *  - Empty cohort renders as em-dash, not "0%" or NaN.
 */
import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
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
  safety_netting_denominator: 42,
  // Care-obstruction fields under test.
  care_obstruction_pct: 21.4,
  care_obstruction_recorded_n: 9,
  care_obstruction_severe_pct: 21.4,
  care_obstruction_severe_n: 9,
  care_obstruction_signal_counts: {
    rejection: 4,
    dna: 5,
    cancellation: 0,
    access_barrier: 0,
    none: 33,
  },
  care_obstruction_denominator: 42,
  care_obstruction_confirmed_n: 3,
  care_obstruction_confirmed_pct: 7.1,
  care_obstruction_confirmed_events: 9,
  care_obstruction_unrelated_filtered_events: 2,
};

describe("AuditSummarySection — care obstructions tile", () => {
  it("renders the headline rate from care_obstruction_pct", () => {
    render(
      <AuditSummarySection
        summary={baseSummary}
        loading={false}
        orgName="Demo Practice"
        totalCases={65}
      />,
    );
    expect(screen.getByText("Potential care delays")).toBeInTheDocument();
    expect(screen.getByText("21.4%")).toBeInTheDocument();
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
      screen.getByText("9 of 42 confirmed cancers"),
    ).toBeInTheDocument();
  });

  it("surfaces the pathway-confirmed and filtered-as-unrelated counts in the tooltip", () => {
    /**
     * The relatedness telemetry must be exposed on the tile tooltip
     * so an auditor can see how aggressive the filter is without
     * leaving the snapshot view.  MUI Tooltip mounts its body on
     * hover/focus, so we trigger mouseOver on the value first.
     */
    jest.useFakeTimers();
    render(
      <AuditSummarySection
        summary={baseSummary}
        loading={false}
        orgName="Demo Practice"
      />,
    );

    const label = screen.getByText("Potential care delays");
    fireEvent.mouseOver(label);
    fireEvent.mouseEnter(label);
    act(() => {
      jest.advanceTimersByTime(500);
    });

    expect(
      screen
        .getAllByText(
          (_, node) =>
            (node?.textContent ?? "").includes("Pathway-confirmed") &&
            (node?.textContent ?? "").includes("3/42"),
        )
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen
        .getAllByText(
          (_, node) =>
            (node?.textContent ?? "").includes("Filtered as unrelated:") &&
            (node?.textContent ?? "").includes(
              "2 events from non-cancer services",
            ),
        )
        .length,
    ).toBeGreaterThan(0);
    jest.useRealTimers();
  });

  it("falls back to the descriptive subtext when the breakdown is absent", () => {
    const summary: AuditSummary = {
      ...baseSummary,
      care_obstruction_recorded_n: undefined,
      care_obstruction_denominator: undefined,
      care_obstruction_signal_counts: undefined,
    };
    render(
      <AuditSummarySection
        summary={summary}
        loading={false}
        orgName="Demo Practice"
      />,
    );
    expect(
      screen.getByText(
        "Pathways with rejected referral, DNA, cancellation or access barrier",
      ),
    ).toBeInTheDocument();
  });

  it("renders an em-dash when the rate is null (no confirmed cancers)", () => {
    const summary: AuditSummary = {
      ...baseSummary,
      care_obstruction_pct: null,
      care_obstruction_recorded_n: 0,
      care_obstruction_severe_pct: null,
      care_obstruction_severe_n: 0,
      care_obstruction_signal_counts: {
        rejection: 0,
        dna: 0,
        cancellation: 0,
        access_barrier: 0,
        none: 0,
      },
      care_obstruction_denominator: 0,
    };
    render(
      <AuditSummarySection
        summary={summary}
        loading={false}
        orgName="Demo Practice"
      />,
    );
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
