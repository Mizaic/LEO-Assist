/**
 * Teach this form -- bidirectional section focus matching.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */

import * as fs from "fs";
import * as path from "path";

import {
  matchSectionFromLetterText,
  regionsFromSections,
} from "../components/operations/formSchemaSectionFocus";
import type { FormSchemaSection } from "../components/operations/formSchemaDetector";

const OPS = path.join(__dirname, "../components/operations");

function section(
  sectionId: string,
  label: string,
  items: string[] = [],
): FormSchemaSection {
  return {
    section_id: sectionId,
    section_type: "checkbox_single",
    label,
    start_pattern: "",
    items: items.map((pattern) => ({
      pattern,
      entity_text: pattern,
      semantic_tag: "finding",
      assertion: "present",
    })),
  };
}

const SECTIONS = [
  section("A", "Section A: Gynaecological Cancer type suspected", [
    "Ovary",
    "Cervix",
  ]),
  section("B", "Section B: Signs/symptoms for 14-day rule criteria", [
    "Lesion suspicious of cancer of cervix",
  ]),
  section("C", "Section C: Further Clinical details"),
];

describe("matchSectionFromLetterText", () => {
  it("matches section_id from a Section A heading before item text", () => {
    const hit = matchSectionFromLetterText(
      SECTIONS,
      "Section A: Gynaecological Cancer type suspected Ovary Cervix",
    );
    expect(hit?.section_id).toBe("A");
  });

  it("matches section_id from a bare region id", () => {
    expect(matchSectionFromLetterText(SECTIONS, "B")?.section_id).toBe("B");
  });

  it("matches label text when there is no section letter", () => {
    const named = [
      section("MDS", "Minimum Dataset"),
      section("A", "Section A: Gynaecological Cancer type suspected"),
    ];
    expect(
      matchSectionFromLetterText(named, "Minimum Dataset")?.section_id,
    ).toBe("MDS");
  });

  it("matches an item label_pattern such as Cervix", () => {
    expect(matchSectionFromLetterText(SECTIONS, "Cervix")?.section_id).toBe("A");
  });

  it("prefers section_id over a later item pattern", () => {
    const hit = matchSectionFromLetterText(
      SECTIONS,
      "Section B: Signs/symptoms including Cervix",
    );
    expect(hit?.section_id).toBe("B");
  });

  it("returns undefined when nothing matches (no-op)", () => {
    expect(matchSectionFromLetterText(SECTIONS, "xyzzy-no-match")).toBeUndefined();
    expect(matchSectionFromLetterText(SECTIONS, "")).toBeUndefined();
    expect(matchSectionFromLetterText([], "Section A")).toBeUndefined();
  });
});

describe("regionsFromSections", () => {
  it("uses section_id as the letter region id and includes heading plus items", () => {
    const regions = regionsFromSections(SECTIONS);
    const regionA = regions.find((r) => r.regionId === "A");
    expect(regionA?.label).toMatch(/Section A/);
    expect(regionA?.itemPatterns).toEqual(expect.arrayContaining(["Ovary", "Cervix"]));
  });
});

describe("Teach this form section focus wiring", () => {
  const dialog = fs.readFileSync(
    path.join(OPS, "ExtractionQualityReviewDialog.tsx"),
    "utf8",
  );
  const annotator = fs.readFileSync(
    path.join(OPS, "FormSchemaAnnotator.tsx"),
    "utf8",
  );
  const editor = fs.readFileSync(
    path.join(OPS, "FormSchemaSectionEditor.tsx"),
    "utf8",
  );
  const focus = fs.readFileSync(
    path.join(OPS, "formSchemaSectionFocus.ts"),
    "utf8",
  );

  it("dialog wires highlighted region id onto the letter pane", () => {
    expect(dialog).toMatch(/useTeachFormSectionFocus/);
    expect(dialog).toMatch(/highlightedRegionId/);
    expect(dialog).toMatch(/data-highlighted-region/);
    expect(dialog).toMatch(/focusedSectionId/);
  });

  it("annotator selects a section and reports sections to the letter", () => {
    expect(annotator).toMatch(/focusedSectionId/);
    expect(annotator).toMatch(/onSelectSection/);
    expect(annotator).toMatch(/onSectionsChange/);
  });

  it("section card highlight is not colour-only", () => {
    expect(editor).toMatch(/aria-current/);
    expect(editor).toMatch(/form-schema-section-card/);
    expect(editor).toMatch(/borderColor/);
    expect(editor).toMatch(/Enter/);
  });

  it("new focus helpers do not paste HEX colours", () => {
    expect(focus).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
  });
});
