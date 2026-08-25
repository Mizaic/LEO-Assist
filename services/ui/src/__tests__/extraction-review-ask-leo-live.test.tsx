/**
 * VT-CE7006EE -- live Ask LEO on a selected draft fact.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { FactList } from "../components/operations/ExtractionReviewFacts";
import { askLeoSmart, searchTerms } from "../lib/api/legacy";

jest.mock("../lib/api/legacy", () => ({
  askLeoSmart: jest.fn(),
  searchTerms: jest.fn(),
}));

const theme = createTheme();

describe("FactList Ask LEO", () => {
  beforeEach(() => {
    jest.mocked(searchTerms).mockResolvedValue([
      {
        snomed_concept_id: "271939006",
        term: "Vaginal discharge",
        semantic_tag: "finding",
      },
    ]);
    jest.mocked(askLeoSmart).mockResolvedValue({
      matched_candidate: {
        snomed_concept_id: "271939006",
        term: "Vaginal discharge",
        semantic_tag: "finding",
      },
      reason: "The letter names vaginal discharge as a current symptom.",
      is_ambiguous: false,
      alternative_query_used: null,
      assertion_warning: null,
      assertion: "present",
    });
  });

  it("asks LEO and applies the tag only after the reviewer accepts", async () => {
    const user = userEvent.setup();
    const onPatch = jest.fn();
    render(
      <ThemeProvider theme={theme}>
        <FactList
          entities={[
            { text: "vaginal discharge", semantic_tag: "", assertion: "present" },
          ]}
          letterText="Thank you for seeing this lady with vaginal discharge"
          pickedText="vaginal discharge"
          onPick={jest.fn()}
          onRemove={jest.fn()}
          onPatch={onPatch}
        />
      </ThemeProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Ask LEO" }));
    expect(
      await screen.findByText("The letter names vaginal discharge as a current symptom."),
    ).toBeInTheDocument();
    expect(onPatch).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Use this tag" }));
    expect(onPatch).toHaveBeenCalledWith("vaginal discharge", {
      semantic_tag: "finding",
      assertion: "present",
    });
  });
});
