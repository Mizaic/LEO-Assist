import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReviewCard from "../ReviewCard";
import type { ReviewItem } from "../ReviewCard";

jest.mock("@/lib/api/legacy", () => ({
  askLeoSmart: jest.fn(),
  searchTerms: jest.fn(),
}));
jest.mock("@/components/operations/CodingReviewCasesModal", () => {
  return function MockModal() {
    return null;
  };
});

const hitlItem: ReviewItem = {
  id: "R1",
  kind: "hitl",
  entityText: "chest pain",
  entityLabel: "disorder",
  count: 3,
  confidence: 0.9,
  uncoded: false,
  question: "Is this a valid finding?",
  explanation: "LEO detected chest pain.",
  decisionTier: 2,
  tierReason: "medium_confidence",
  tierDecision: "review",
};

function renderReviewCard(
  item: ReviewItem,
  overrides?: Partial<{
    onResolveCoding: jest.Mock;
    onResolveHitl: jest.Mock;
    onSkip: jest.Mock;
    onAllCasesResolved: jest.Mock;
    busy: boolean;
  }>
) {
  const defaults = {
    onResolveCoding: jest.fn(),
    onResolveHitl: jest.fn(),
    onSkip: jest.fn(),
    onAllCasesResolved: jest.fn(),
    busy: false,
  };
  const props = { ...defaults, ...overrides };
  render(
    <ReviewCard
      item={item}
      onResolveCoding={props.onResolveCoding}
      onResolveHitl={props.onResolveHitl}
      onSkip={props.onSkip}
      onAllCasesResolved={props.onAllCasesResolved}
      busy={props.busy}
    />
  );
  return props;
}

describe("ReviewCard — HitlActions", () => {
  it("Dismiss button opens ConfirmDialog", async () => {
    const user = userEvent.setup();
    renderReviewCard(hitlItem);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.getByText("Dismiss this review item?")).toBeInTheDocument();
  });

  it("Confirming dismiss calls onResolveHitl with 'dismissed'", async () => {
    const user = userEvent.setup();
    const { onResolveHitl } = renderReviewCard(hitlItem);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Dismiss" }));
    expect(onResolveHitl).toHaveBeenCalledWith(hitlItem, "dismissed");
  });

  it("Cancelling dismiss closes dialog", async () => {
    const user = userEvent.setup();
    renderReviewCard(hitlItem);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.getByText("Dismiss this review item?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Dismiss this review item?")).not.toBeInTheDocument();
  });

  it("Approve calls onResolveHitl with 'resolved'", async () => {
    const user = userEvent.setup();
    const { onResolveHitl } = renderReviewCard(hitlItem);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(onResolveHitl).toHaveBeenCalledWith(hitlItem, "resolved");
  });
});

describe("ReviewCard — TierBadge", () => {
  it("renders tier badge when decisionTier is set", () => {
    const itemWithTier: ReviewItem = { ...hitlItem, decisionTier: 1 };
    renderReviewCard(itemWithTier);
    expect(screen.getByText("Tier 1")).toBeInTheDocument();
  });
});
