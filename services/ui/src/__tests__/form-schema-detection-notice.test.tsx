/**
 * VT: whole-letter form detection with a visible fallback.
 *
 * The teacher must be told when a simpler reader stood in for Ask LEO,
 * and the browser reader must find numbered SECTION 1 / 2 / 3 headings.
 *
 * Atlas trace: VT-25098971, DI-C1744ED5, DO-1C8E7598, R-98702FED
 */
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";

import { FormSchemaDetectionNotice } from "../components/operations/FormSchemaDetectionNotice";
import {
  BROWSER_READER_NOTICE,
  chooseDetection,
} from "../components/operations/formSchemaDetectChoice";
import {
  detectSections,
  type FormSchemaSection,
} from "../components/operations/formSchemaDetector";

const REPO_ROOT = path.resolve(__dirname, "../../../..");
const LOWER_GI = fs.readFileSync(
  path.join(REPO_ROOT, "tests/fixtures/form_schema/sfh_lower_gi_2ww_full_deid.md"),
  "utf8",
);

function readSource(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

function clinical(id: string): FormSchemaSection {
  return {
    section_id: id,
    section_type: "checkbox_multi",
    label: `Section ${id}`,
    start_pattern: `Section ${id}`,
    items: [],
  };
}

describe("browser reader finds numbered sections", () => {
  test("SECTION 1, 2 and 3 are found in letter order", () => {
    const numbered = detectSections(LOWER_GI)
      .filter((s) => /^section\s+\d/i.test(s.label))
      .map((s) => s.section_id);
    expect(numbered).toEqual(["1", "2", "3"]);
  });

  test("SECTION 1 demographics is typed admin, SECTION 3 is kept", () => {
    const byId = new Map(detectSections(LOWER_GI).map((s) => [s.section_id, s]));
    expect(byId.get("1")?.section_type).toBe("admin");
    expect(byId.get("3")?.section_type).not.toMatch(/admin|template_noise/);
  });

  test("section ids are unique", () => {
    const ids = detectSections(LOWER_GI).map((s) => s.section_id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("chooseDetection", () => {
  test("keeps the server answer and its notice", () => {
    const local = jest.fn(() => [clinical("L")]);
    const choice = chooseDetection(
      { sections: [clinical("A")], notice: "This letter is too long." },
      local,
    );
    expect(choice.sections[0].section_id).toBe("A");
    expect(choice.notice).toBe("This letter is too long.");
    expect(local).not.toHaveBeenCalled();
  });

  test("shows a notice instead of clearing it when the browser reader is used", () => {
    const choice = chooseDetection({ sections: [], notice: "" }, () => [clinical("L")]);
    expect(choice.sections[0].section_id).toBe("L");
    expect(choice.notice).toBe(BROWSER_READER_NOTICE);
    expect(choice.notice.toLowerCase()).toContain("check every section");
  });

  test("keeps the server notice when nothing could be found", () => {
    const choice = chooseDetection(
      { sections: [], notice: "We could not find any sections." },
      () => [],
    );
    expect(choice.sections).toEqual([]);
    expect(choice.notice).toBe("We could not find any sections.");
  });
});

describe("FormSchemaDetectionNotice", () => {
  const theme = createTheme();

  test("renders the notice as a status message", () => {
    render(
      <ThemeProvider theme={theme}>
        <FormSchemaDetectionNotice message="Check every section before you save." />
      </ThemeProvider>,
    );
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Check every section before you save.");
  });

  test("renders nothing when there is no notice", () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <FormSchemaDetectionNotice message="" />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("teach dialog wiring", () => {
  test("the hook reads the detection notice from the API and returns it", () => {
    const src = readSource("services/ui/src/components/operations/useFormSchemaTeach.ts");
    expect(src).toMatch(/payload\.detection\?\.message/);
    expect(src).toMatch(/chooseDetection\(/);
    expect(src).toMatch(/notice:\s*state\.notice/);
  });

  test("the annotator shows the notice", () => {
    const src = readSource("services/ui/src/components/operations/FormSchemaAnnotator.tsx");
    expect(src).toMatch(/<FormSchemaDetectionNotice\s+message=\{teach\.notice\}/);
  });
});
