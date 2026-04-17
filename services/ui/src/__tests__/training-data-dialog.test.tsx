/**
 * VT-LEO-AI-144 -- Wave E Phase 2a-iv
 *
 * Verifies the redesigned GoldLabelDetailDialog chrome:
 *
 *   - GoldDatasetPanel imports the four new sub-components from
 *     services/ui/src/components/gold-dataset/GoldLabelDetailDialog/.
 *   - The legacy <DialogTitle> "Review this example" header has been
 *     swapped for <DialogTitleStrip>.
 *   - The legacy <DialogActions> footer (with Close + Delete + Skip +
 *     Accept-all-and-mark + Mark-as-gold cluster) has been swapped
 *     for <DialogActionsBar>.
 *   - The legacy "Recommended links" inline box has been replaced
 *     with <SuggestionsPanel>.
 *   - Inline Delete confirm panel has been replaced with
 *     <DeleteConfirmPanel>.
 *
 * Then a focused render test exercises each sub-component to prove
 * acceptance criteria from DI-LEO-AI-145:
 *   AC-001 Single primary action in the footer.
 *   AC-002 Status pill summarises uncoded + suggested counts.
 *   AC-003 Delete is hidden behind a kebab (progressive disclosure).
 *   AC-004 SuggestionsPanel collapses cleanly when count == 0.
 *   AC-005 Primary action label morphs when suggestions are pending.
 */
import fs from "fs";
import path from "path";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

import DialogTitleStrip from "@/components/gold-dataset/GoldLabelDetailDialog/DialogTitleStrip";
import DialogActionsBar from "@/components/gold-dataset/GoldLabelDetailDialog/DialogActionsBar";
import SuggestionsPanel from "@/components/gold-dataset/GoldLabelDetailDialog/SuggestionsPanel";
import DeleteConfirmPanel from "@/components/gold-dataset/GoldLabelDetailDialog/DeleteConfirmPanel";

const PANEL_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "gold-dataset",
  "GoldDatasetPanel.tsx",
);

describe("VT-LEO-AI-144 GoldLabelDetailDialog chrome redesign", () => {
  let source: string;

  beforeAll(() => {
    source = fs.readFileSync(PANEL_PATH, "utf8");
  });

  it("TC-001: panel imports the four new dialog sub-components", () => {
    expect(source).toMatch(
      /from\s+"@\/components\/gold-dataset\/GoldLabelDetailDialog\/DialogTitleStrip"/,
    );
    expect(source).toMatch(
      /from\s+"@\/components\/gold-dataset\/GoldLabelDetailDialog\/DialogActionsBar"/,
    );
    expect(source).toMatch(
      /from\s+"@\/components\/gold-dataset\/GoldLabelDetailDialog\/SuggestionsPanel"/,
    );
    expect(source).toMatch(
      /from\s+"@\/components\/gold-dataset\/GoldLabelDetailDialog\/DeleteConfirmPanel"/,
    );
  });

  it("TC-002: panel renders the new chrome elements inside the dialog", () => {
    expect(source).toMatch(/<DialogTitleStrip\b/);
    expect(source).toMatch(/<DialogActionsBar\b/);
    expect(source).toMatch(/<SuggestionsPanel\b/);
    expect(source).toMatch(/<DeleteConfirmPanel\b/);
  });

  it("TC-003: legacy 'Review this example' DialogTitle and Accept-all/Mark cluster are gone", () => {
    expect(source).not.toMatch(/<Typography[^>]*>\s*Review this example/);
    expect(source).not.toMatch(/Accept all and mark as gold/);
  });

  it("TC-004: status pill shows ready when no work, work-counts otherwise (AC-002)", () => {
    const { rerender } = render(
      <DialogTitleStrip
        title="Review this example"
        uncodedCount={0}
        suggestionCount={0}
        hasGuidelines={false}
        guidelinesOpen={false}
        shortcutsOpen={false}
        copied={false}
        onCopySentence={() => {}}
        onToggleGuidelines={() => {}}
        onToggleShortcuts={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("dialog-status-pill")).toHaveTextContent(
      /Ready to mark gold/,
    );

    rerender(
      <DialogTitleStrip
        title="Review this example"
        uncodedCount={3}
        suggestionCount={2}
        hasGuidelines
        guidelinesOpen={false}
        shortcutsOpen={false}
        copied={false}
        onCopySentence={() => {}}
        onToggleGuidelines={() => {}}
        onToggleShortcuts={() => {}}
        onClose={() => {}}
      />,
    );
    const pill = screen.getByTestId("dialog-status-pill");
    expect(pill).toHaveTextContent(/3 need code/);
    expect(pill).toHaveTextContent(/2 suggested/);
    expect(screen.getByTestId("dialog-guidelines-toggle")).toBeInTheDocument();
  });

  it("TC-005: footer renders ONE primary action and Delete is behind a kebab (AC-001/AC-003)", () => {
    const noop = () => {};
    render(
      <DialogActionsBar
        saving={false}
        markingGold={false}
        pendingSuggestionCount={0}
        canMarkGold
        canDelete
        canSkip
        onMarkGold={noop}
        onAcceptAllAndMark={noop}
        onSkipNext={noop}
        onRequestDelete={noop}
      />,
    );
    const primary = screen.getByTestId("dialog-primary-action");
    expect(primary).toHaveTextContent(/Mark as gold/);
    expect(screen.getByTestId("dialog-skip-button")).toBeInTheDocument();
    expect(screen.getByTestId("dialog-more-actions")).toBeInTheDocument();
    expect(screen.queryByText(/Delete this sentence/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("dialog-more-actions"));
    expect(
      screen.getByTestId("dialog-delete-menu-item"),
    ).toBeInTheDocument();
  });

  it("TC-006: primary action label morphs when suggestions are pending (AC-005)", () => {
    const noop = () => {};
    render(
      <DialogActionsBar
        saving={false}
        markingGold={false}
        pendingSuggestionCount={4}
        canMarkGold
        canDelete={false}
        canSkip={false}
        onMarkGold={noop}
        onAcceptAllAndMark={noop}
        onSkipNext={noop}
        onRequestDelete={noop}
      />,
    );
    const primary = screen.getByTestId("dialog-primary-action");
    expect(primary).toHaveAttribute("data-morph", "accept-and-mark");
    expect(primary).toHaveTextContent(/Accept 4 \+ mark as gold/);
  });

  it("TC-007: SuggestionsPanel renders nothing when there are zero suggestions (AC-004)", () => {
    const { container } = render(
      <SuggestionsPanel
        suggestions={[]}
        entities={[]}
        rejectedKeys={{}}
        saving={false}
        onAccept={() => {}}
        onReject={() => {}}
        onUndoReject={() => {}}
        onAcceptAll={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("TC-008: SuggestionsPanel exposes Accept-all and renders rows", () => {
    const accepted: string[] = [];
    render(
      <SuggestionsPanel
        suggestions={[
          {
            sourceIdx: 0,
            targetIdx: 1,
            type: "finding_site",
            confidence: 0.88,
            reason: "Findings co-occur with body sites",
          },
        ]}
        entities={[
          { text: "ulcer", label: "finding" } as any,
          { text: "leg", label: "body_site" } as any,
        ]}
        rejectedKeys={{}}
        saving={false}
        onAccept={(s) => accepted.push(`${s.sourceIdx}:${s.type}:${s.targetIdx}`)}
        onReject={() => {}}
        onUndoReject={() => {}}
        onAcceptAll={() => {}}
      />,
    );
    expect(screen.getByTestId("suggestions-panel")).toBeInTheDocument();
    const acceptAll = screen.getByTestId("suggestions-accept-all");
    expect(acceptAll).toHaveTextContent(/Accept all/);
    fireEvent.click(screen.getByTestId("suggestion-accept-0:finding_site:1"));
    expect(accepted).toEqual(["0:finding_site:1"]);
  });

  it("TC-009: DeleteConfirmPanel toggles label between Delete and Delete-and-block", () => {
    const { rerender } = render(
      <DeleteConfirmPanel
        suppressOnDelete={false}
        onSuppressChange={() => {}}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByTestId("delete-confirm-button")).toHaveTextContent(
      /^Delete$/,
    );
    rerender(
      <DeleteConfirmPanel
        suppressOnDelete
        onSuppressChange={() => {}}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByTestId("delete-confirm-button")).toHaveTextContent(
      /Delete and block/,
    );
  });
});
