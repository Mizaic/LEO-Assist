/**
 * Live-render regression -- stale AI-generation warnings hidden once a
 * rule leaves pending_review.
 *
 * generation_outcome and generation_errors are written once at AI
 * generation time and never updated by an approve/reject/edit decision.
 * Once a rule is no longer pending_review, the "Needs manual authoring"
 * chip and the "AI generation did not finish" banner must not render,
 * since they would otherwise show a stale diagnostic on an already
 * reviewed rule.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339.
 */

import React from "react";
import { render, screen } from "@testing-library/react";

import { RuleAccordionCard } from "../RuleReviewCard";
import type { Rule, RuleStatusFilter } from "../ruleReviewTypes";

const CHIP_TEXT = /Needs manual authoring/i;
const BANNER_TEXT = /AI generation did not finish for this recommendation/i;

function makeRule(status: string): Rule {
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
    generation_outcome: "extraction_failed",
    generation_errors: ["Could not extract criteria from recommendation text."],
  };
}

function renderCard(status: string) {
  return render(
    <RuleAccordionCard
      rule={makeRule(status)}
      expanded
      busy={null}
      index={0}
      statusFilter={status as RuleStatusFilter}
      callbacks={{ onToggle: () => undefined, onEdit: () => undefined }}
    />,
  );
}

describe("RuleAccordionCard - stale AI-generation warnings gated on status", () => {
  it("hides the generation-outcome chip and the generation banner for an active (approved) rule", () => {
    renderCard("active");
    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();
    expect(screen.queryByText(BANNER_TEXT)).not.toBeInTheDocument();
  });

  it("shows the generation-outcome chip and the generation banner for a pending_review rule", () => {
    renderCard("pending_review");
    expect(screen.getByText(CHIP_TEXT)).toBeInTheDocument();
    expect(screen.getByText(BANNER_TEXT)).toBeInTheDocument();
  });
});
