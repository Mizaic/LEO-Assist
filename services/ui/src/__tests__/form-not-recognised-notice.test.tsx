/**
 * Live-render VT: a paused task for an unrecognised form tells the reviewer
 * what happened and what to do next.
 *
 * The notice shows the plain-English copy, the closest taught form, the
 * headings we could not find, and a Teach this form action. A failed form
 * check says a person must check the letter. A recognised form shows
 * nothing.
 *
 * Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";

import FormRecognitionNotice from "../components/operations/FormRecognitionNotice";
import {
  FORM_NOT_RECOGNISED_COPY,
  pauseReasonLabel,
} from "../components/operations/extractionReviewCopy";

const DIALOG_SRC = readFileSync(
  join(__dirname, "../components/operations/ExtractionQualityReviewDialog.tsx"),
  "utf8",
);

const MISSING = ["Section C", "Section D", "Section E", "Section F", "Section G", "Section H", "Section I"];

const UNRECOGNISED = {
  outcome: "unrecognised",
  title: "Gynae referral",
  chunk_indexes: [0],
  reason: "form_not_recognised",
  best: {
    fingerprint: "sfh-gynae-2ww-v1",
    form_name: "Sherwood gynae 2WW",
    matched: ["Section A", "Section B"],
    missing: MISSING,
  },
  runner_up: null,
};

function renderNotice(rows: unknown[], onTeach = jest.fn()) {
  render(
    <ThemeProvider theme={createTheme()}>
      <FormRecognitionNotice rows={rows} onTeach={onTeach} />
    </ThemeProvider>,
  );
  return onTeach;
}

describe("form not recognised notice", () => {
  it("says what happened and what to do next", () => {
    renderNotice([UNRECOGNISED]);
    expect(screen.getByText(FORM_NOT_RECOGNISED_COPY)).toBeInTheDocument();
    expect(FORM_NOT_RECOGNISED_COPY).toBe(
      "We did not recognise this form. Teach it, then run extraction again.",
    );
  });

  it("names the closest taught form and how many headings it found", () => {
    renderNotice([UNRECOGNISED]);
    expect(
      screen.getByText(/Closest taught form: Sherwood gynae 2WW\. We found 2 of its 9 headings\./),
    ).toBeInTheDocument();
  });

  it("lists the missing headings, capped so the list stays short", () => {
    renderNotice([UNRECOGNISED]);
    const line = screen.getByText(/Headings we could not find:/);
    expect(line.textContent).toContain("Section C, Section D, Section E, Section F, Section G");
    expect(line.textContent).toContain("and 2 more");
    expect(line.textContent).not.toContain("Section H");
  });

  it("says no taught form came close when there is no best match", () => {
    renderNotice([{ ...UNRECOGNISED, best: null }]);
    expect(screen.getByText("No taught form came close.")).toBeInTheDocument();
  });

  it("the Teach this form action opens teaching", async () => {
    const onTeach = renderNotice([UNRECOGNISED]);
    await userEvent.click(screen.getByRole("button", { name: "Teach this form" }));
    expect(onTeach).toHaveBeenCalledTimes(1);
  });

  it("a failed form check says a person must check the letter", () => {
    renderNotice([{ outcome: "recognition_failed", title: "", chunk_indexes: [0], error: "x" }]);
    expect(
      screen.getByText("We could not check which form this is. Check the letter yourself before it goes on."),
    ).toBeInTheDocument();
    expect(screen.queryByText("x")).toBeNull();
  });

  it("a recognised form shows no notice", () => {
    renderNotice([{ outcome: "recognised", title: "", chunk_indexes: [0], fingerprint: "fp" }]);
    expect(screen.queryByTestId("form-recognition-notice")).toBeNull();
  });

  it("the pause reason chip reads in plain English", () => {
    expect(pauseReasonLabel("form_not_recognised")).toBe("We did not recognise this form");
  });

  it("the review dialog reads form_recognition and opens Teach from the notice", () => {
    expect(DIALOG_SRC).toMatch(/raw\.form_recognition/);
    expect(DIALOG_SRC).toMatch(/<FormRecognitionNotice[\s\S]*?onTeach=\{\(\) => setRightTab\("teach"\)\}/);
  });
});
