/**
 * Static-source VT for FormSchemaAnnotator and formSchemaDetector.
 *
 * Tests the auto-detection logic as unit tests (pure functions).
 * Tests the component file structure as static-source assertions.
 *
 * Atlas trace: DI-5C9CA57B
 */

import * as fs from "fs";
import * as path from "path";

const OPS = path.join(
  __dirname,
  "../components/operations",
);
const ANNOTATOR_SRC = fs.readFileSync(
  path.join(OPS, "FormSchemaAnnotator.tsx"),
  "utf8",
);
const DETECTOR_SRC = fs.readFileSync(
  path.join(OPS, "formSchemaDetector.ts"),
  "utf8",
);

// ---------------------------------------------------------------------------
// Static-source invariants: FormSchemaAnnotator.tsx
// ---------------------------------------------------------------------------

describe("FormSchemaAnnotator.tsx static-source invariants", () => {
  it("exports FormSchemaAnnotator as default or named export", () => {
    expect(
      ANNOTATOR_SRC.includes("export default function FormSchemaAnnotator") ||
        ANNOTATOR_SRC.includes("export function FormSchemaAnnotator"),
    ).toBe(true);
  });

  it("accepts fingerprint and sourceText as props", () => {
    expect(ANNOTATOR_SRC).toContain("fingerprint");
    expect(ANNOTATOR_SRC).toContain("sourceText");
  });

  it("fetches schema from /api/form-schemas/", () => {
    expect(ANNOTATOR_SRC).toContain("/api/form-schemas/");
  });

  it("supports PUT to save schema", () => {
    expect(ANNOTATOR_SRC).toContain('"PUT"');
  });

  it("renders a section type selector", () => {
    expect(
      ANNOTATOR_SRC.includes("section_type") ||
        ANNOTATOR_SRC.includes("sectionType"),
    ).toBe(true);
  });

  it("renders item entity_text fields for checkbox sections", () => {
    expect(
      ANNOTATOR_SRC.includes("entity_text") ||
        ANNOTATOR_SRC.includes("entityText"),
    ).toBe(true);
  });

  it("has a Save schema button", () => {
    expect(
      ANNOTATOR_SRC.toLowerCase().includes("save") &&
        ANNOTATOR_SRC.includes("schema"),
    ).toBe(true);
  });

  it("does not use snapshot testing", () => {
    expect(ANNOTATOR_SRC).not.toContain("toMatchSnapshot");
  });
});

// ---------------------------------------------------------------------------
// Static-source invariants: formSchemaDetector.ts
// ---------------------------------------------------------------------------

describe("formSchemaDetector.ts static-source invariants", () => {
  it("exports detectSections function", () => {
    expect(DETECTOR_SRC).toContain("export function detectSections");
  });

  it("defines SECTION_TYPE literals", () => {
    expect(DETECTOR_SRC).toContain("checkbox_single");
    expect(DETECTOR_SRC).toContain("checkbox_yesno");
    expect(DETECTOR_SRC).toContain("free_text");
    expect(DETECTOR_SRC).toContain("ordered_tests");
    expect(DETECTOR_SRC).toContain("scale");
    expect(DETECTOR_SRC).toContain("admin");
    expect(DETECTOR_SRC).toContain("template_noise");
  });

  it("exports FormSchemaSection type or interface", () => {
    expect(
      DETECTOR_SRC.includes("export type FormSchemaSection") ||
        DETECTOR_SRC.includes("export interface FormSchemaSection"),
    ).toBe(true);
  });

  it("exports FormSchemaItem type or interface", () => {
    expect(
      DETECTOR_SRC.includes("export type FormSchemaItem") ||
        DETECTOR_SRC.includes("export interface FormSchemaItem"),
    ).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Unit tests for auto-detection logic
// Loaded from the compiled module via require / dynamic import simulation.
// Because detectSections is pure (no DOM / network), we can exercise it
// directly via ts-jest.
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { detectSections } = require(
  "../components/operations/formSchemaDetector",
) as { detectSections: (text: string) => Array<{ section_type: string; label: string; items: unknown[] }> };

const GYNAE_FORM = `
Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]

Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
B2. Lesion suspicious on vulva | Yes [ ] No [X]

Section C: Further Clinical details
BMI: 20.2 Vaginal discharge 10/7 yellowish colour. Polyp noted.

Section D: Investigations performed
MANDATORY tests: FBC LFTs UEs Calcium
BLOODS DONE TODAY

Section E: PERFORMANCE STATUS
Clinical Frailty Scale 1. Very Fit [X] 2. Fit [ ] 3. Managing well [ ]
`;

describe("detectSections auto-detection", () => {
  it("detects Section A as checkbox_single", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionA = sections.find((s) => s.section_id === "A");
    expect(sectionA).toBeDefined();
    expect(sectionA?.section_type).toBe("checkbox_single");
  });

  it("detects Section B as checkbox_yesno", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionB = sections.find((s) => s.section_id === "B");
    expect(sectionB).toBeDefined();
    expect(sectionB?.section_type).toBe("checkbox_yesno");
  });

  it("detects Section C as free_text", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionC = sections.find((s) => s.section_id === "C");
    expect(sectionC).toBeDefined();
    expect(sectionC?.section_type).toBe("free_text");
  });

  it("detects Section D as ordered_tests", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionD = sections.find((s) => s.section_id === "D");
    expect(sectionD).toBeDefined();
    expect(sectionD?.section_type).toBe("ordered_tests");
  });

  it("detects Section E as scale", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionE = sections.find((s) => s.section_id === "E");
    expect(sectionE).toBeDefined();
    expect(sectionE?.section_type).toBe("scale");
  });

  it("returns at least one section per labelled section header", () => {
    const sections = detectSections(GYNAE_FORM);
    expect(sections.length).toBeGreaterThanOrEqual(5);
  });

  it("returns empty array for empty text", () => {
    expect(detectSections("")).toEqual([]);
  });

  it("detects checkbox items in section_type checkbox_single", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionA = sections.find((s) => s.section_id === "A");
    expect(sectionA?.items.length).toBeGreaterThan(0);
  });

  it("detects yes/no items in section_type checkbox_yesno", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionB = sections.find((s) => s.section_id === "B");
    expect(sectionB?.items.length).toBeGreaterThan(0);
  });

  it("returns no items for free_text sections", () => {
    const sections = detectSections(GYNAE_FORM);
    const sectionC = sections.find((s) => s.section_id === "C");
    expect(sectionC?.items).toEqual([]);
  });
});
