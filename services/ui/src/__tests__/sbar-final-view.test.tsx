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
 *   - source-record IDs are read from the typed ``backgroundParts``
 *     prop (NOT parsed out of the markdown body) and surfaced behind
 *     a per-section "Show source records" disclosure that defaults
 *     to collapsed
 *   - any legacy ``<!-- sources: ... -->`` HTML comments embedded in
 *     a persisted markdown body are stripped from the rendered view
 *     so old Assessments do not leak raw UUIDs into the UI
 */
import "@testing-library/jest-dom";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  SbarFinalDialog,
  SbarFinalView,
  splitFinalSbar,
  stripSourceComments,
  STAGE_THEME,
  type SbarBackgroundPart,
  type CompletenessFinding,
} from "@/components/sbar-final";

const SAMPLE = `# SBAR

## Situation

This 74-year-old male patient has a clinic appointment scheduled.

## Background

### Part 1 of 2 -- records 1-3

- **Metastatic prostate cancer** [2025-09-05]
- **PSA 129 ng/mL** [August 2025]

### Part 2 of 2 -- records 4-5

- Follow-up clinic note from oncology

## Assessment

_No matching guideline rules fired._

## Recommendation

Refer urgently under the suspected lung cancer 2WW pathway.
`;

const SAMPLE_BACKGROUND_PARTS: SbarBackgroundPart[] = [
  {
    index: 1,
    total: 2,
    recordCount: 3,
    recordRange: [1, 3],
    sourceIds: ["enc-001", "enc-002", "doc-007"],
    status: "completed",
    errorCode: null,
    errorMessage: null,
  },
  {
    index: 2,
    total: 2,
    recordCount: 2,
    recordRange: [4, 5],
    sourceIds: ["enc-019", "doc-021"],
    status: "completed",
    errorCode: null,
    errorMessage: null,
  },
];

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

describe("stripSourceComments", () => {
  it("removes a standalone <!-- sources: ... --> line", () => {
    const md =
      "### Part 1 of 1 -- records 1-2\n<!-- sources: a, b -->\n\n- bullet";
    expect(stripSourceComments(md)).not.toMatch(/<!--/);
    expect(stripSourceComments(md)).toContain("- bullet");
    expect(stripSourceComments(md)).toContain("Part 1 of 1");
  });

  it("removes inline <!-- sources --> comments mid-paragraph", () => {
    const md = "prose <!-- sources: x --> more prose";
    expect(stripSourceComments(md)).toBe("prose  more prose");
  });

  it("is a no-op when the body has no sources comment", () => {
    expect(stripSourceComments("- bullet\n- bullet")).toBe(
      "- bullet\n- bullet",
    );
  });

  it("returns falsy input unchanged", () => {
    expect(stripSourceComments("")).toBe("");
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

  it("always shows the AI advisory disclaimer regardless of testOnly flag", () => {
    const { rerender } = render(<SbarFinalView markdown={SAMPLE} />);
    expect(
      screen.getByTestId("sbar-final-advisory-disclaimer"),
    ).toBeInTheDocument();

    rerender(<SbarFinalView markdown={SAMPLE} testOnly={false} />);
    expect(
      screen.getByTestId("sbar-final-advisory-disclaimer"),
    ).toBeInTheDocument();
  });

  it("advisory disclaimer contains the required statutory advisory text", () => {
    render(<SbarFinalView markdown={SAMPLE} />);
    const banner = screen.getByTestId("sbar-final-advisory-disclaimer");
    expect(banner).toHaveTextContent(/AI-generated summary/);
    expect(banner).toHaveTextContent(/Clinician review required/);
    expect(banner).toHaveTextContent(/decision support aid/);
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

  it("hides the source-records disclosure when no backgroundParts are passed", () => {
    render(<SbarFinalView markdown={SAMPLE} />);
    expect(
      screen.queryByTestId("sbar-final-section-background-sources"),
    ).toBeNull();
  });

  it("only mounts the source-records disclosure on the Background card", () => {
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={SAMPLE_BACKGROUND_PARTS}
      />,
    );
    expect(
      screen.getByTestId("sbar-final-section-background-sources"),
    ).toBeInTheDocument();
    for (const stage of [
      "situation",
      "assessment",
      "recommendation",
    ] as const) {
      expect(
        screen.queryByTestId(`sbar-final-section-${stage}-sources`),
      ).toBeNull();
    }
  });

  it("source-records disclosure starts collapsed and reveals chips on click", async () => {
    const user = userEvent.setup();
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={SAMPLE_BACKGROUND_PARTS}
      />,
    );
    const totalIds = SAMPLE_BACKGROUND_PARTS.reduce(
      (acc, p) => acc + p.sourceIds.length,
      0,
    );
    const toggle = screen.getByTestId(
      "sbar-final-section-background-sources-toggle",
    );
    expect(toggle).toHaveTextContent(`Show source records (${totalIds})`);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("enc-001")).toBeNull();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveTextContent(`Hide source records (${totalIds})`);
    for (const id of [
      "enc-001",
      "enc-002",
      "doc-007",
      "enc-019",
      "doc-021",
    ]) {
      expect(screen.getByText(id)).toBeInTheDocument();
    }
    // Each part group inside the disclosure carries a caption
    // showing its part heading. Scope the lookup so the matching
    // ``### Part ...`` heading inside the rendered markdown body
    // does not trip a multi-match.
    const part0 = screen.getByTestId(
      "sbar-final-section-background-sources-part-0",
    );
    expect(
      within(part0).getByText(/Part 1 of 2 -- records 1-3/),
    ).toBeInTheDocument();
    const part1 = screen.getByTestId(
      "sbar-final-section-background-sources-part-1",
    );
    expect(
      within(part1).getByText(/Part 2 of 2 -- records 4-5/),
    ).toBeInTheDocument();
  });

  it("source-records disclosure is hidden when backgroundParts has zero source ids", () => {
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={[
          {
            ...SAMPLE_BACKGROUND_PARTS[0],
            sourceIds: [],
          },
        ]}
      />,
    );
    expect(
      screen.queryByTestId("sbar-final-section-background-sources"),
    ).toBeNull();
  });

  it("source-records chips coerce non-string source ids without crashing", async () => {
    const user = userEvent.setup();
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={[
          {
            ...SAMPLE_BACKGROUND_PARTS[0],
            // Wire payloads occasionally deliver Neo4j integers.
            sourceIds: [42 as unknown as string, "enc-safe"],
          },
        ]}
      />,
    );
    await user.click(
      screen.getByTestId("sbar-final-section-background-sources-toggle"),
    );
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("enc-safe")).toBeInTheDocument();
  });

  it("clicking an enriched source chip opens a dialog with the exact record text", async () => {
    const user = userEvent.setup();
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={[
          {
            ...SAMPLE_BACKGROUND_PARTS[0],
            sourceIds: ["chunk-full-1"],
            sources: [
              {
                id: "chunk-full-1",
                type: "Chunk",
                label: "Referral letter chunk 1",
                preview: "Dear Colleague,",
                fullText:
                  "Dear Colleague,\n\nThank you for referring this patient " +
                  "with iron-deficiency anaemia. Full letter text continues.",
              },
            ],
          },
        ]}
      />,
    );
    await user.click(
      screen.getByTestId("sbar-final-section-background-sources-toggle"),
    );
    await user.click(screen.getByText("Referral letter chunk 1"));
    expect(
      screen.getByTestId("sbar-final-section-background-source-dialog-body"),
    ).toHaveTextContent(
      "Thank you for referring this patient with iron-deficiency anaemia",
    );
    expect(
      screen.getByTestId("sbar-final-section-background-source-dialog-note"),
    ).toHaveTextContent(/exact record text/i);
    expect(screen.getByText(/Technical id: chunk-full-1/)).toBeInTheDocument();
  });

  it("falls back to the short preview when a source has no fullText", async () => {
    const user = userEvent.setup();
    render(
      <SbarFinalView
        markdown={SAMPLE}
        backgroundParts={[
          {
            ...SAMPLE_BACKGROUND_PARTS[0],
            sourceIds: ["enc-legacy"],
            sources: [
              {
                id: "enc-legacy",
                type: "Encounter",
                label: "Encounter (legacy)",
                preview: "Progressive jaundice.",
              },
            ],
          },
        ]}
      />,
    );
    await user.click(
      screen.getByTestId("sbar-final-section-background-sources-toggle"),
    );
    await user.click(screen.getByText("Encounter (legacy)"));
    expect(
      screen.getByTestId("sbar-final-section-background-source-dialog-body"),
    ).toHaveTextContent("Progressive jaundice.");
    expect(
      screen.getByTestId("sbar-final-section-background-source-dialog-note"),
    ).toHaveTextContent(/short preview only/i);
  });

  it("does not show the completeness chip when completenessFinding is not supplied", () => {
    render(<SbarFinalView markdown={SAMPLE} />);
    expect(
      screen.queryByTestId("sbar-final-completeness-chip"),
    ).toBeNull();
  });

  it("shows a completeness chip in the Background header when completenessFinding is supplied", () => {
    const finding: CompletenessFinding = {
      requiredFields: ["Diagnosis", "Urgency", "Weight"],
      presentFields: ["Diagnosis", "Urgency"],
      missingFields: ["Weight"],
      unclearFields: [],
    };
    render(<SbarFinalView markdown={SAMPLE} completenessFinding={finding} />);
    const chip = screen.getByTestId("sbar-final-completeness-chip");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent("67%");
  });

  it("shows 100% chip when all required fields are present", () => {
    const finding: CompletenessFinding = {
      requiredFields: ["Diagnosis"],
      presentFields: ["Diagnosis"],
      missingFields: [],
      unclearFields: [],
    };
    render(<SbarFinalView markdown={SAMPLE} completenessFinding={finding} />);
    expect(screen.getByTestId("sbar-final-completeness-chip")).toHaveTextContent("100%");
  });

  it("does not render a legacy <!-- sources: --> HTML comment as visible text", () => {
    const legacyMarkdown = `## Background

### Part 1 of 1 -- records 1-2

<!-- sources: legacy-uuid-001, legacy-uuid-002 -->

- bullet body
`;
    render(<SbarFinalView markdown={legacyMarkdown} />);
    expect(
      screen.queryByText(/legacy-uuid-001/),
    ).toBeNull();
    expect(
      screen.queryByText(/<!-- sources/),
    ).toBeNull();
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

  it("forwards backgroundParts to the embedded view", () => {
    render(
      <SbarFinalDialog
        open
        onClose={() => {}}
        markdown={SAMPLE}
        backgroundParts={SAMPLE_BACKGROUND_PARTS}
      />,
    );
    expect(
      screen.getByTestId("sbar-final-section-background-sources"),
    ).toBeInTheDocument();
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
