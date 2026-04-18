/**
 * VT-LEO-AI-194 -- SbarFinalView / SbarFinalDialog standalone contract
 *
 * The SBAR (final) renderer was extracted from SbarPlayground into a
 * reusable component (services/ui/src/components/sbar-final/) so other
 * applications can embed the same view.
 *
 * This test pins the public contract:
 *   - splitFinalSbar splits a SBAR Markdown payload by section heading
 *     and is robust to extra/whitespace headings
 *   - the view renders one themed card per section, in canonical SBAR
 *     order, regardless of source order
 *   - falls back to a single rendered Markdown block when no SBAR
 *     headings are present
 *   - the dialog wrapper exposes open/onClose, the test-only chip is
 *     visible by default, and "Copy Markdown" copies the source markdown
 *     to the clipboard
 */
import "@testing-library/jest-dom";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  SbarFinalDialog,
  SbarFinalView,
  splitFinalSbar,
  STAGE_THEME,
} from "@/components/sbar-final";

const SAMPLE = `# SBAR

## Situation

This 74-year-old male patient has a clinic appointment scheduled.

## Background

- **Metastatic prostate cancer** [2025-09-05]
- **PSA 129 ng/mL** [August 2025]

## Assessment

_No matching guideline rules fired._

## Recommendation

Refer urgently under the suspected lung cancer 2WW pathway.
`;

describe("splitFinalSbar", () => {
  it("returns one entry per SBAR section in canonical order", () => {
    const sections = splitFinalSbar(SAMPLE);
    expect(sections.map((s) => s.stage)).toEqual([
      "situation",
      "background",
      "assessment",
      "recommendation",
    ]);
  });

  it("trims surrounding blank lines from each section body", () => {
    const sections = splitFinalSbar(SAMPLE);
    for (const s of sections) {
      expect(s.body.startsWith("\n")).toBe(false);
      expect(s.body.endsWith("\n")).toBe(false);
    }
  });

  it("returns canonical SBAR order even if input is shuffled", () => {
    const shuffled = [
      "## Recommendation\nDo X.",
      "## Situation\nWho.",
      "## Background\nWhy.",
      "## Assessment\nSo what.",
    ].join("\n\n");
    const sections = splitFinalSbar(shuffled);
    expect(sections.map((s) => s.stage)).toEqual([
      "situation",
      "background",
      "assessment",
      "recommendation",
    ]);
  });

  it("returns an empty array when no SBAR headings are present", () => {
    expect(splitFinalSbar("just some prose, no headings")).toEqual([]);
  });

  it("ignores unknown ## headings", () => {
    const sections = splitFinalSbar(
      "## Misc\nignored\n\n## Situation\nkept",
    );
    expect(sections).toHaveLength(1);
    expect(sections[0].stage).toBe("situation");
    expect(sections[0].body).toBe("kept");
  });

  it("matches headings case-insensitively", () => {
    const sections = splitFinalSbar(
      "## SITUATION\nA\n\n## background\nB",
    );
    expect(sections.map((s) => s.stage)).toEqual([
      "situation",
      "background",
    ]);
  });
});

describe("SbarFinalView", () => {
  it("renders one themed card per SBAR section", () => {
    render(<SbarFinalView markdown={SAMPLE} />);
    for (const stage of [
      "situation",
      "background",
      "assessment",
      "recommendation",
    ] as const) {
      expect(
        screen.getByTestId(`sbar-final-section-${stage}`),
      ).toBeInTheDocument();
    }
  });

  it("shows the test-only banner by default and hides it when disabled", () => {
    const { rerender } = render(<SbarFinalView markdown={SAMPLE} />);
    expect(
      screen.getByTestId("sbar-final-test-only-banner"),
    ).toBeInTheDocument();

    rerender(<SbarFinalView markdown={SAMPLE} testOnly={false} />);
    expect(
      screen.queryByTestId("sbar-final-test-only-banner"),
    ).toBeNull();
  });

  it("falls back to a single Markdown block when no SBAR headings are present", () => {
    render(<SbarFinalView markdown="# Just a heading\n\nProse." />);
    for (const stage of [
      "situation",
      "background",
      "assessment",
      "recommendation",
    ] as const) {
      expect(
        screen.queryByTestId(`sbar-final-section-${stage}`),
      ).toBeNull();
    }
    expect(
      screen.getByTestId("sbar-final-content"),
    ).toBeInTheDocument();
  });

  it("renders an empty-state message when markdown is missing", () => {
    render(<SbarFinalView markdown="" />);
    expect(screen.getByTestId("sbar-final-empty")).toBeInTheDocument();
  });

  it("respects testIdPrefix so embedders can mount multiple views", () => {
    render(<SbarFinalView markdown={SAMPLE} testIdPrefix="my-sbar" />);
    expect(
      screen.getByTestId("my-sbar-section-situation"),
    ).toBeInTheDocument();
  });
});

describe("SbarFinalDialog", () => {
  it("does not render content when open=false", () => {
    render(
      <SbarFinalDialog
        open={false}
        onClose={() => {}}
        markdown={SAMPLE}
      />,
    );
    expect(screen.queryByTestId("sbar-final-dialog")).toBeNull();
  });

  it("renders themed sections inside the dialog when open", () => {
    render(
      <SbarFinalDialog open onClose={() => {}} markdown={SAMPLE} />,
    );
    const dialog = screen.getByTestId("sbar-final-dialog");
    for (const stage of [
      "situation",
      "background",
      "assessment",
      "recommendation",
    ] as const) {
      expect(
        within(dialog).getByTestId(`sbar-final-section-${stage}`),
      ).toBeInTheDocument();
    }
  });

  it("invokes onClose from both the close icon and the footer Close button", async () => {
    const onClose = jest.fn();
    render(
      <SbarFinalDialog open onClose={onClose} markdown={SAMPLE} />,
    );
    const user = userEvent.setup();

    // Close icon (top-right) -- pinned via test-id.
    await user.click(screen.getByTestId("sbar-final-dialog-close"));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Both the icon button and the footer button expose the
    // accessible name "Close"; the footer button is the second match.
    const closeButtons = screen.getAllByRole("button", {
      name: /^Close$/,
    });
    expect(closeButtons.length).toBeGreaterThanOrEqual(2);
    await user.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("copies the markdown payload to the clipboard via the Copy button", async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    render(
      <SbarFinalDialog open onClose={() => {}} markdown={SAMPLE} />,
    );
    // userEvent.setup() installs its own clipboard implementation; we
    // override AFTER setup so the component's call lands on our spy.
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    await user.click(screen.getByTestId("sbar-final-dialog-copy"));
    expect(writeText).toHaveBeenCalledWith(SAMPLE);
  });
});

describe("STAGE_THEME palette", () => {
  it("exposes accent + tint + ink colours for every SBAR stage", () => {
    for (const stage of [
      "situation",
      "background",
      "assessment",
      "recommendation",
    ] as const) {
      expect(STAGE_THEME[stage]).toEqual(
        expect.objectContaining({
          accent: expect.any(String),
          tint: expect.any(String),
          ink: expect.any(String),
        }),
      );
    }
  });
});
