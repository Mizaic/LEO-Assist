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
    expect(
      screen.queryByText("The letter names vaginal discharge as a current symptom."),
    ).not.toBeInTheDocument();
  });

  it("moves to the next unset fact after the reviewer accepts a tag", async () => {
    const user = userEvent.setup();
    const onPick = jest.fn();
    render(
      <ThemeProvider theme={theme}>
        <FactList
          entities={[
            { text: "vaginal discharge", semantic_tag: "", assertion: "present" },
            { text: "cervix", semantic_tag: "", assertion: "present" },
          ]}
          letterText="vaginal discharge and cervix"
          pickedText="vaginal discharge"
          onPick={onPick}
          onRemove={jest.fn()}
          onPatch={jest.fn()}
        />
      </ThemeProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Ask LEO" }));
    await screen.findByRole("button", { name: "Use this tag" });
    await user.click(screen.getByRole("button", { name: "Use this tag" }));
    expect(onPick).toHaveBeenCalledWith("cervix");
  });

  it("removes a form label and moves to the next unset fact", async () => {
    const user = userEvent.setup();
    const onRemove = jest.fn();
    const onPick = jest.fn();
    const onPatch = jest.fn();
    render(
      <ThemeProvider theme={theme}>
        <FactList
          entities={[
            {
              text: "Discharge patient and reassure",
              semantic_tag: "",
              assertion: "present",
            },
            { text: "BMI: 20.2 Kg/m2", semantic_tag: "", assertion: "present" },
          ]}
          letterText="Discharge patient and reassure. BMI: 20.2 Kg/m2"
          pickedText="Discharge patient and reassure"
          onPick={onPick}
          onRemove={onRemove}
          onPatch={onPatch}
        />
      </ThemeProvider>,
    );

    await user.click(screen.getByRole("button", { name: "This is a label" }));
    expect(onPatch).not.toHaveBeenCalled();
    expect(onRemove).toHaveBeenCalledWith("Discharge patient and reassure");
    expect(onPick).toHaveBeenCalledWith("BMI: 20.2 Kg/m2");
  });
});
