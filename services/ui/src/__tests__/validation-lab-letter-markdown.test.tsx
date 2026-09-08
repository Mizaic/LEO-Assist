/**
 * Formatted letter markdown in Validation Lab run review.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 *
 * Atlas trace:
 *   DO: DO-4FD76836
 *   DI: DI-C953EF73
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4FD76836")
 */

import { render, screen } from "@testing-library/react";

import LetterPane from "../app/admin/validation-lab/LetterPane";
import LetterMarkdownView from "../app/admin/validation-lab/LetterMarkdownView";
import {
  parseLetterMarkdown,
  splitLetterSource,
} from "../app/admin/validation-lab/letterMarkdown";

const SAMPLE = `--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology.doc ---

Dear Gynaecology team,

Re: suspected **cervix** cancer on speculum examination.

## Blood Results

| Panel | Result |
| --- | --- |
| FBC | Hb 117 g/L |
`;

describe("splitLetterSource", () => {
  it("lifts the Document header into a file name", () => {
    const split = splitLetterSource(SAMPLE);
    expect(split.filename).toBe(
      "23 Jun 2026 Two Week Wait Referral to Gynaecology.doc",
    );
    expect(split.body).not.toMatch(/--- Document:/);
    expect(split.body).toContain("Dear Gynaecology team");
  });
});

describe("parseLetterMarkdown", () => {
  it("parses headings, tables, and bold", () => {
    const blocks = parseLetterMarkdown(splitLetterSource(SAMPLE).body);
    expect(blocks.some((block) => block.type === "heading")).toBe(true);
    expect(blocks.some((block) => block.type === "table")).toBe(true);
    const paragraph = blocks.find((block) => block.type === "paragraph");
    expect(paragraph?.type).toBe("paragraph");
  });
});

describe("VT-F0A6B9F4 - letter markdown is formatted", () => {
  it("hides the Document header dashes and shows the file name", () => {
    render(<LetterPane referralText={SAMPLE} />);
    expect(screen.queryByText(/--- Document:/)).not.toBeInTheDocument();
    expect(screen.getByTestId("validation-lab-letter-filename")).toHaveTextContent(
      "23 Jun 2026 Two Week Wait Referral to Gynaecology.doc",
    );
  });

  it("renders headings and tables instead of markdown marks", () => {
    render(<LetterPane referralText={SAMPLE} />);
    expect(screen.queryByText(/## Blood Results/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Blood Results" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Panel" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Hb 117 g/L" })).toBeInTheDocument();
    expect(screen.queryByText(/\*\*cervix\*\*/)).not.toBeInTheDocument();
    expect(screen.getByText("cervix").closest("strong")).not.toBeNull();
  });

  it("still highlights stage facts on the formatted letter", () => {
    render(
      <LetterPane
        referralText={SAMPLE}
        highlights={[
          {
            term: "cervix",
            assertion: "present",
            semanticTag: "finding",
          },
        ]}
      />,
    );
    const mark = screen.getByTestId("validation-lab-letter-highlight");
    expect(mark).toHaveTextContent("cervix");
    expect(mark).toHaveAttribute("data-semantic-tag", "finding");
  });

  it("formats a GP note through the same letter renderer", () => {
    render(
      <LetterMarkdownView
        text={"## Note\n\nPatient **well**."}
        emptyLabel="No note"
      />,
    );
    expect(screen.getByRole("heading", { name: "Note" })).toBeInTheDocument();
    expect(screen.queryByText(/\*\*well\*\*/)).not.toBeInTheDocument();
  });
});
