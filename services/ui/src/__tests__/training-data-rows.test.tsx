/**
 * VT-LEO-AI-143 -- Wave E Phase 2a-iii
 *
 * Verifies that the row-level surface of the Training Data tab is
 * unified across the three sub-tabs:
 *   - Candidates renders through CandidateReviewList -> ReviewListCard.
 *   - Verified gold renders through GoldLabelReviewList -> ReviewListCard.
 *   - Synthetic re-uses the same GoldLabelReviewList (single code path).
 *   - The legacy GoldLabelRow is no longer wired in by the panel.
 *   - RelationRow's "no links" indicator is rendered as a quiet
 *     dashed pill rather than a saturated orange MUI Chip.
 *
 * The GoldDatasetPanel is a 4,781 LOC monolith with many runtime
 * dependencies; full DOM render tests for it are deferred to Phase 2b.
 * This VT therefore mixes a focused render test on the new pieces
 * (GoldLabelRowActions, RelationRow) with a static-source assertion
 * on the panel wiring.
 */
import fs from "fs";
import path from "path";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import RelationRow from "@/components/gold-dataset/RelationRow";
import {
  QualityChip,
  GoldRowMenu,
} from "@/components/gold-dataset/GoldLabelRowActions";

const PANEL_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "gold-dataset",
  "GoldDatasetPanel.tsx"
);

describe("VT-LEO-AI-143 Training Data row redesign on ReviewListCard", () => {
  let source: string;

  beforeAll(() => {
    source = fs.readFileSync(PANEL_PATH, "utf8");
  });

  it("TC-001: panel imports GoldLabelReviewList and not the legacy GoldLabelRow", () => {
    expect(source).toMatch(/from\s+"@\/components\/gold-dataset\/GoldLabelReviewList"/);
    expect(source).not.toMatch(/from\s+"@\/components\/gold-dataset\/GoldLabelRow"/);
  });

  it("TC-002: panel renders GoldLabelReviewList for the gold/synthetic tabs", () => {
    expect(source).toMatch(/<GoldLabelReviewList\b/);
    expect(source).not.toMatch(/<GoldLabelRow\b/);
  });

  it("TC-003: candidates tab still renders through CandidateReviewList", () => {
    expect(source).toMatch(
      /tab\s*===\s*"candidates"[\s\S]{0,400}?<CandidateReviewList\b/
    );
  });

  it("TC-004: QualityChip renders with the correct tone bucket", () => {
    const { rerender } = render(<QualityChip score={0.91} />);
    const chip = screen.getByTestId("gold-quality-chip");
    expect(chip).toHaveAttribute("data-tone", "positive");
    expect(chip).toHaveTextContent("91%");

    rerender(<QualityChip score={0.61} />);
    expect(screen.getByTestId("gold-quality-chip")).toHaveAttribute(
      "data-tone",
      "warning"
    );

    rerender(<QualityChip score={0.32} />);
    expect(screen.getByTestId("gold-quality-chip")).toHaveAttribute(
      "data-tone",
      "danger"
    );

    rerender(<QualityChip score={null} />);
    const neutral = screen.getByTestId("gold-quality-chip");
    expect(neutral).toHaveAttribute("data-tone", "neutral");
    expect(neutral).toHaveTextContent("verified");
  });

  it("TC-005: GoldRowMenu exposes the Reset action behind progressive disclosure", () => {
    render(
      <GoldRowMenu
        labelId="abc"
        resetting={false}
        disabled={false}
        onReset={() => undefined}
      />
    );
    const trigger = screen.getByTestId("gold-row-menu-abc");
    expect(trigger).toHaveAttribute("aria-label", "More actions");
  });

  it("TC-006: RelationRow renders the quiet 'no links' indicator without an MUI Chip", () => {
    render(<RelationRow triplets={[]} missing={true} />);
    const indicator = screen.getByText(/no links/i);
    expect(indicator).toBeInTheDocument();
    // The new design is a span styled inline, NOT an MuiChip.
    const chipParent = indicator.closest(".MuiChip-root");
    expect(chipParent).toBeNull();
  });

  it("TC-007: RelationRow renders nothing when there is no signal to convey", () => {
    const { container } = render(<RelationRow triplets={[]} missing={false} />);
    expect(container.firstChild).toBeNull();
  });
});
