/**
 * LivePreviewPane -- 3-column NICE original / Before / After Save review.
 * Atlas: DI-LEO-AI-234 / DO-LEO-AI-234 / VT-LEO-AI-510
 */
import React from "react";
import { render, screen } from "@testing-library/react";

import LivePreviewPane from "../LivePreviewPane";
import type { RuleSummary } from "../treeToSentence";

const AFTER_SUMMARY: RuleSummary = {
  lead: "If the patient is 40 years or older and has a cough.",
  isWellShaped: true,
};

const BEFORE_SUMMARY: RuleSummary = {
  lead: "If the patient has a cough.",
  isWellShaped: true,
};

const NEW_RULE_SUMMARY: RuleSummary = {
  lead: "This rule has no conditions yet. Add a symptom, procedure, situation, or patient detail to get started.",
  isWellShaped: false,
};

describe("LivePreviewPane -- plain live preview (not Save step)", () => {
  it("renders a single live-preview card with no NICE original / before columns", () => {
    render(<LivePreviewPane summary={AFTER_SUMMARY} actions={[]} />);
    expect(screen.getByText(/live preview/i)).toBeInTheDocument();
    expect(screen.queryByText(/nice original/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/before your change/i)).not.toBeInTheDocument();
  });
});

describe("LivePreviewPane -- Save step 3-column review", () => {
  it("renders NICE original, Before, and After columns when recommendationText is supplied", () => {
    render(
      <LivePreviewPane
        summary={AFTER_SUMMARY}
        actions={[]}
        showBeforeAfter
        beforeSummary={BEFORE_SUMMARY}
        recommendationText="Offer an urgent chest X-ray in people aged 40 and over with a cough."
      />,
    );
    expect(screen.getByText(/nice original/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Offer an urgent chest X-ray in people aged 40 and over/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/before your change/i)).toBeInTheDocument();
    expect(screen.getByText(/after your change/i)).toBeInTheDocument();
    expect(screen.getByText(BEFORE_SUMMARY.lead)).toBeInTheDocument();
    expect(screen.getByText(AFTER_SUMMARY.lead)).toBeInTheDocument();
  });

  it("omits the NICE original column (falls back to 2-column) when there is no NICE source text", () => {
    render(
      <LivePreviewPane
        summary={AFTER_SUMMARY}
        actions={[]}
        showBeforeAfter
        beforeSummary={BEFORE_SUMMARY}
        recommendationText={null}
      />,
    );
    expect(screen.queryByText(/nice original/i)).not.toBeInTheDocument();
    expect(screen.getByText(/before your change/i)).toBeInTheDocument();
    expect(screen.getByText(/after your change/i)).toBeInTheDocument();
  });

  it("shows the reading-age-appropriate blank placeholder in the Before column for a brand-new rule", () => {
    render(
      <LivePreviewPane
        summary={AFTER_SUMMARY}
        actions={[]}
        showBeforeAfter
        beforeSummary={NEW_RULE_SUMMARY}
        recommendationText="Offer an urgent chest X-ray."
      />,
    );
    expect(screen.getByText(/this rule has no conditions yet/i)).toBeInTheDocument();
  });

  it("does not render the 3-column review at all when beforeSummary is missing", () => {
    render(
      <LivePreviewPane
        summary={AFTER_SUMMARY}
        actions={[]}
        showBeforeAfter
        recommendationText="Offer an urgent chest X-ray."
      />,
    );
    expect(screen.queryByText(/nice original/i)).not.toBeInTheDocument();
    expect(screen.getByText(/live preview/i)).toBeInTheDocument();
  });
});
