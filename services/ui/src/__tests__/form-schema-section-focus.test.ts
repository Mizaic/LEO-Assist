/**
 * Teach this form -- bidirectional section focus matching.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */

import * as fs from "fs";
import * as path from "path";

import {
  buildFreeTextBodyLineOwners,
  matchSectionFromLetterText,
  regionHitForText,
  regionsFromSections,
  cleanLetterSelectionText,
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

  it("matches row identifier prefix B1 to Section B", () => {
    expect(matchSectionFromLetterText(SECTIONS, "B1. Lesion suspicious")?.section_id).toBe("B");
  });

  it("matches row identifier B2 (no dot) to Section B", () => {
    expect(matchSectionFromLetterText(SECTIONS, "B2 Any lesion")?.section_id).toBe("B");
  });

  it("matches A3. prefix to Section A", () => {
    expect(matchSectionFromLetterText(SECTIONS, "A3. Ovary (please tick)")?.section_id).toBe("A");
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

describe("buildFreeTextBodyLineOwners", () => {
  const freeTextSections: FormSchemaSection[] = [
    {
      section_id: "ACI",
      section_type: "free_text",
      label: "Additional clinical information",
      start_pattern: "(?i)additional\\s+clinical\\s+information",
      items: [],
    },
  ];

  it("maps prose lines below a free_text heading to that section", () => {
    const letter = [
      "Additional clinical information",
      "Patient has postmenopausal bleeding for 3 months.",
      "Polyp noted on examination.",
    ].join("\n");
    const owners = buildFreeTextBodyLineOwners(letter, freeTextSections);
    expect(owners.get("Patient has postmenopausal bleeding for 3 months.")).toBe(
      "ACI",
    );
    expect(owners.get("Polyp noted on examination.")).toBe("ACI");
  });

  it("regionHitForText resolves free_text body lines via the owner map", () => {
    const letter = [
      "Additional clinical information",
      "Patient has postmenopausal bleeding for 3 months.",
    ].join("\n");
    const regions = regionsFromSections(freeTextSections);
    const owners = buildFreeTextBodyLineOwners(letter, freeTextSections);
    const hit = regionHitForText(
      regions,
      "Patient has postmenopausal bleeding for 3 months.",
      owners,
    );
    expect(hit?.regionId).toBe("ACI");
    expect(hit?.primary).toBe(false);
  });

  it("a start pattern with brackets matches its own heading as plain text (DI-C1744ED5)", () => {
    const sections: FormSchemaSection[] = [
      {
        section_id: "RAD",
        section_type: "free_text",
        label: "Radiology",
        start_pattern: "Radiology: (In last 6 months)",
        items: [],
      },
    ];
    const letter = ["| Radiology: (In last 6 months) |", "CT colon booked."].join("\n");
    const owners = buildFreeTextBodyLineOwners(letter, sections);
    expect(owners.get("CT colon booked.")).toBe("RAD");
  });
});

describe("cleanLetterSelectionText", () => {
  it("strips a B1. row prefix", () => {
    expect(cleanLetterSelectionText("B1. Lesion site")).toBe("Lesion site");
  });

  it("strips a B2 row prefix without dot", () => {
    expect(cleanLetterSelectionText("B2 Any lesion")).toBe("Any lesion");
  });

  it("strips trailing parenthetical noise", () => {
    expect(cleanLetterSelectionText("Cervix (please tick)")).toBe("Cervix");
  });

  it("leaves plain text unchanged", () => {
    expect(cleanLetterSelectionText("Cervical cancer suspected")).toBe("Cervical cancer suspected");
  });

  it("strips single-letter-dot prefix like A. ", () => {
    expect(cleanLetterSelectionText("A. Any lesion")).toBe("Any lesion");
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

  it("dialog handles teach-mode text selection and routes it to annotator", () => {
    expect(dialog).toMatch(/pendingSelection/);
    expect(dialog).toMatch(/onPendingConsumed/);
    expect(dialog).toMatch(/handleTeachSelection/);
    expect(dialog).toMatch(/onTeachSelection/);
  });

  it("dialog shows hint when no section is focused and selection cannot be matched", () => {
    expect(dialog).toMatch(/selectionHint/);
    expect(dialog).toMatch(/teach-selection-hint/);
    expect(dialog).toMatch(/Select a section/);
  });

  it("annotator accepts pendingSelection and addItemWithContent", () => {
    expect(annotator).toMatch(/pendingSelection/);
    expect(annotator).toMatch(/onPendingConsumed/);
    expect(annotator).toMatch(/addItemWithContent/);
  });

  it("teach mode mouseup fires onTeachSelection not fact-add", () => {
    expect(dialog).toMatch(/teachMode.*onTeachSelection|onTeachSelection.*teachMode/);
  });
});
