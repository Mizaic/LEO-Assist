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
const TEACH_SRC = [
  ANNOTATOR_SRC,
  ...fs
    .readdirSync(OPS)
    .filter(
      (name) =>
        /^(FormSchema|formSchema|useFormSchema)/.test(name) &&
        (name.endsWith(".tsx") || name.endsWith(".ts")),
    )
    .map((name) => fs.readFileSync(path.join(OPS, name), "utf8")),
].join("\n");

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

  it("calls /api/form-schemas/detect POST for LLM auto-detect", () => {
    expect(TEACH_SRC).toContain("/api/form-schemas/detect");
    expect(TEACH_SRC).toContain('"POST"');
  });

  it("shows LEO is reading the form during load", () => {
    expect(ANNOTATOR_SRC).toContain("LEO is reading the form");
  });

  it("supports PUT to save schema", () => {
    expect(TEACH_SRC).toContain('"PUT"');
  });

  it("renders a section type selector", () => {
    expect(
      TEACH_SRC.includes("section_type") ||
        TEACH_SRC.includes("sectionType"),
    ).toBe(true);
  });

  it("renders item entity_text fields for checkbox sections", () => {
    expect(
      TEACH_SRC.includes("entity_text") ||
        TEACH_SRC.includes("entityText"),
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

  it("shows a visible Add section control when auto-detect finds nothing", () => {
    expect(TEACH_SRC).toMatch(/Add section/);
  });

  it("surfaces detect HTTP errors instead of a silent empty state", () => {
    expect(TEACH_SRC).toMatch(/setError\(/);
    expect(TEACH_SRC).toMatch(/detect\.ok|!detect\.ok|res\.ok/);
  });

  it("does not tell the reviewer a missing button will appear below", () => {
    expect(TEACH_SRC).not.toMatch(/using the button below/);
  });

  it("does not hide Add section behind a client role gate", () => {
    expect(TEACH_SRC).not.toMatch(/useRole|RoleGate|selected_role/);
  });

  it("proxies /api/form-schemas/ to core-api", () => {
    const proxySrc = fs.readFileSync(
      path.join(__dirname, "../proxy.ts"),
      "utf8",
    );
    expect(proxySrc).toMatch(/prefix:\s*["']\/api\/form-schemas\//);
    expect(proxySrc).toMatch(/["']\/api\/form-schemas\/:path\*/);
    expect(proxySrc).toMatch(/\$\{coreApi\(\)\}\/form-schemas\//);
  });

  it("clears the hard detect error when local fallback finds sections", () => {
    const teachHook = fs.readFileSync(
      path.join(OPS, "useFormSchemaTeach.ts"),
      "utf8",
    );
    expect(teachHook).toMatch(/localDetectOrEmpty/);
    expect(teachHook).toMatch(/isIncompleteSchema/);
    expect(teachHook).toMatch(/setError\(\s*["']["']\s*\)/);
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

  it("detects Section A without a colon as a section header", () => {
    const text =
      "Section A Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]";
    const sections = detectSections(text);
    expect(sections.find((s) => s.section_id === "A")).toBeDefined();
  });

  it("detects Section A and B inside markdown table cells", () => {
    const text = [
      "Minimum Dataset",
      "NHS Number: 718 563 0207",
      "| Section A: Gynaecological Cancer type suspected |",
      "| --- |",
      "| Ovary [ ] Cervix [X] Endometrium [ ] |",
      "| Section B: Signs/symptoms for 14-day rule criteria |",
      "| B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ] |",
    ].join("\n");
    const sections = detectSections(text);
    expect(sections.find((s) => s.section_id === "A")).toBeDefined();
    expect(sections.find((s) => s.section_id === "B")).toBeDefined();
    expect(sections.find((s) => /minimum dataset/i.test(s.label))).toBeDefined();
  });

  it("detects Section A inside HTML table markup", () => {
    const text =
      "<table><tr><td>Section A: Gynaecological Cancer type suspected</td></tr>" +
      "<tr><td>Ovary [ ] Cervix [X]</td></tr></table>";
    const sections = detectSections(text);
    expect(sections.find((s) => s.section_id === "A")).toBeDefined();
  });

  it("detects Section A when it is not at the start of a line", () => {
    const text =
      "Patient details Joe Bloggs Section A: Gynaecological Cancer type suspected Ovary [ ] Cervix [X]";
    const sections = detectSections(text);
    expect(sections.find((s) => s.section_id === "A")).toBeDefined();
  });
});

describe("incomplete saved schema helpers", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { isIncompleteSchema } = require(
    "../components/operations/formSchemaTeach",
  ) as {
    isIncompleteSchema: (
      sections: Array<{ section_type: string }>,
    ) => boolean;
  };

  it("treats an admin-only schema as incomplete so detect can retry", () => {
    expect(
      isIncompleteSchema([{ section_type: "admin" }]),
    ).toBe(true);
  });

  it("treats a schema with a clinical section as complete", () => {
    expect(
      isIncompleteSchema([
        { section_type: "admin" },
        { section_type: "checkbox_single" },
      ]),
    ).toBe(false);
  });
});

describe("Ask LEO again control", () => {
  it("exposes a visible Ask LEO again action on the teach form", () => {
    expect(TEACH_SRC).toMatch(/Ask LEO again/);
    expect(TEACH_SRC).toMatch(/retryDetect|askLeoAgain|forceDetect/);
  });

  it("does not treat an admin-only saved schema as a finished load", () => {
    const teachHook = fs.readFileSync(
      path.join(OPS, "useFormSchemaTeach.ts"),
      "utf8",
    );
    expect(teachHook).toMatch(/isIncompleteSchema/);
    expect(teachHook).toMatch(/tryDetect/);
  });
});
