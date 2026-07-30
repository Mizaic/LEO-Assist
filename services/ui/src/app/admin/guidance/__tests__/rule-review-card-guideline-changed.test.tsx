/**
 * Live-render regression -- "Guideline updated" flag surfaced on an
 * approved rule instead of the guideline check silently retiring it.
 *
 * A NICE re-ingest must never flip an APPROVED (active) rule to
 * superseded on its own -- see NiceGraphUpserter.clear_guideline_content().
 * Instead the rule stays active (still enforced) and is flagged via
 * guideline_text_changed so a reviewer can double check it.
 *
 * Atlas trace: DI-C2DE7FDF / DO-F8CDEBBA / VT-34F3B9C2.
 */

import React from "react";
import { render, screen } from "@testing-library/react";

import { RuleAccordionCard } from "../RuleReviewCard";
import type { Rule, RuleStatusFilter } from "../ruleReviewTypes";

const CHIP_TEXT = /Guideline updated: review recommended/i;

function makeRule(status: string, guidelineTextChanged: boolean): Rule {
  return {
    rule_id: "rule:NG12:test",
    name: "Test rule",
    status,
    strength: "offer",
    guideline_id: "NG12",
    recommendation_text: "Do the thing.",
    plain_english: "Do the thing.",
    present_criteria: [],
    absent_criteria: [],
    has_predecessor: false,
    guideline_text_changed: guidelineTextChanged,
  };
}

function renderCard(status: string, guidelineTextChanged: boolean) {
  return render(
    <RuleAccordionCard
      rule={makeRule(status, guidelineTextChanged)}
      expanded
      busy={null}
      index={0}
      statusFilter={status as RuleStatusFilter}
      callbacks={{ onToggle: () => undefined, onEdit: () => undefined }}
    />
  );
}

describe("RuleAccordionCard - guideline_text_changed flag on approved rules", () => {
  it("shows a review-recommended chip on an active rule flagged by a re-ingest", () => {
    renderCard("active", true);
    expect(screen.getByText(CHIP_TEXT)).toBeInTheDocument();
  });

  it("shows nothing for an active rule that was not flagged", () => {
    renderCard("active", false);
    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();
  });

  it("does not show the chip for a pending_review rule even if flagged", () => {
    // pending_review rules are archived (superseded), not flagged, by
    // ingest -- guideline_text_changed only ever applies to active rules.
    // Guard against the chip leaking onto the wrong status regardless.
    renderCard("pending_review", true);
    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();
  });
});
