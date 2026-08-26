/**
 * Live-render VT: bidirectional section focus on Teach this form.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";

import LetterMarkdownView from "../app/admin/validation-lab/LetterMarkdownView";
import { FormSchemaSectionEditor } from "../components/operations/FormSchemaSectionEditor";
import type { FormSchemaSection } from "../components/operations/formSchemaDetector";
import {
  regionsFromSections,
} from "../components/operations/formSchemaSectionFocus";
import { useTeachFormSectionFocus } from "../components/operations/useTeachFormSectionFocus";

const theme = createTheme();

const LETTER = [
  "Section A: Gynaecological Cancer type suspected",
  "Ovary [ ] Cervix [X] Endometrium [ ]",
  "",
  "Section B: Signs/symptoms for 14-day rule criteria",
  "B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]",
  "",
  "Unrelated narrative about the weather.",
].join("\n");

function sampleSections(): FormSchemaSection[] {
  return [
    {
      section_id: "A",
      section_type: "checkbox_single",
      label: "Section A: Gynaecological Cancer type suspected",
      start_pattern: "",
      items: [
        {
          pattern: "Ovary",
          entity_text: "Ovary",
          semantic_tag: "finding",
          assertion: "present",
        },
        {
          pattern: "Cervix",
          entity_text: "Cervix",
          semantic_tag: "finding",
          assertion: "present",
        },
      ],
    },
    {
      section_id: "B",
      section_type: "checkbox_yesno",
      label: "Section B: Signs/symptoms for 14-day rule criteria",
      start_pattern: "",
      items: [],
    },
  ];
}

function noopPatch() {
  return undefined;
}

function FocusHarness() {
  const sections = sampleSections();
  const focus = useTeachFormSectionFocus();
  return (
    <ThemeProvider theme={theme}>
      <div
        data-testid="extraction-quality-letter"
        data-highlighted-region={focus.highlightedRegionId ?? ""}
      >
        <LetterMarkdownView
          text={LETTER}
          emptyLabel="empty"
          sectionRegions={regionsFromSections(sections)}
          highlightedRegionId={focus.highlightedRegionId}
          onSelectRegion={(regionId, clickedText) =>
            focus.selectLetterText(sections, clickedText || regionId)
          }
        />
      </div>
      {sections.map((section) => (
        <FormSchemaSectionEditor
          key={section.section_id}
          section={section}
          focused={focus.focusedSectionId === section.section_id}
          onSelect={() => focus.selectSection(section)}
          onPatch={noopPatch}
          onPatchItem={noopPatch}
          onAddItem={noopPatch}
          onRemoveItem={noopPatch}
        />
      ))}
    </ThemeProvider>
  );
}

describe("Teach this form bidirectional section focus", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = jest.fn();
  });

  it("selecting a right-hand section sets a highlighted region id on the letter", async () => {
    const user = userEvent.setup();
    render(<FocusHarness />);

    await user.click(screen.getByLabelText(/Form section A/i));

    const letter = screen.getByTestId("extraction-quality-letter");
    expect(letter).toHaveAttribute("data-highlighted-region", "A");
    const highlighted = letter.querySelector("[data-section-highlight='true']");
    expect(highlighted).not.toBeNull();
    expect(highlighted).toHaveAttribute("data-section-region", "A");
    expect(highlighted).toHaveAttribute("aria-current", "true");
  });

  it("selecting a letter heading selects the matching annotator section", async () => {
    const user = userEvent.setup();
    render(<FocusHarness />);

    const heading = screen.getByRole("button", {
      name: /Section B: Signs\/symptoms for 14-day rule criteria/i,
    });
    await user.click(heading);

    const cardB = screen.getByLabelText(/Form section B/i);
    expect(cardB).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("extraction-quality-letter")).toHaveAttribute(
      "data-highlighted-region",
      "B",
    );
  });

  it("no match is a no-op (no crash)", async () => {
    const user = userEvent.setup();
    render(<FocusHarness />);

    await user.click(screen.getByText(/Unrelated narrative about the weather/i));

    expect(screen.getByTestId("extraction-quality-letter")).toHaveAttribute(
      "data-highlighted-region",
      "",
    );
    expect(screen.queryByRole("article", { current: true })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Form section A/i)).not.toHaveAttribute(
      "aria-current",
      "true",
    );
  });
});
