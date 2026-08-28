/**
 * The teach dialog must never hand an unusable section_type back to the API.
 *
 * The local detector is typed, so it cannot produce one. The round trip can:
 * a saved schema or an LLM detect response is cast straight into state and
 * PUT back unchanged. A value such as "checkbox" is not in the normaliser
 * vocabulary, so the deterministic checkbox control does nothing and unticked
 * criteria reach the model as plain text.
 *
 * Atlas trace: DI-5C9CA57B
 */
import { readFileSync } from "fs";
import { join } from "path";
import {
  SAFE_SECTION_TYPE,
  SECTION_TYPES,
  coerceSectionType,
  type FormSchemaSection,
} from "../components/operations/formSchemaDetector";
import { coerceLoadedSections } from "../components/operations/formSchemaTeach";
import { SECTION_TYPE_LABELS } from "../components/operations/FormSchemaSectionEditor";

const TEACH_SRC = readFileSync(
  join(__dirname, "../components/operations/formSchemaTeach.ts"),
  "utf8",
);
const HOOK_SRC = readFileSync(
  join(__dirname, "../components/operations/useFormSchemaTeach.ts"),
  "utf8",
);

function serverSection(sectionType: string): FormSchemaSection {
  return {
    section_id: "section_a_cancer_type",
    section_type: sectionType as FormSchemaSection["section_type"],
    label: "Section A",
    start_pattern: "Section A",
    items: [{ pattern: "Cervix", entity_text: "Suspected cervical cancer", semantic_tag: "finding", assertion: "present" }],
  };
}

describe("section type vocabulary", () => {
  it("checkbox on its own is not a section type", () => {
    expect(SECTION_TYPES).not.toContain("checkbox");
  });

  it("every section type has an editor label, so the dropdown is never blank", () => {
    expect(new Set(Object.keys(SECTION_TYPE_LABELS))).toEqual(new Set(SECTION_TYPES));
  });
});

describe("coerceSectionType", () => {
  it("maps checkbox onto the multiple-choice handler", () => {
    expect(coerceSectionType("checkbox")).toBe("checkbox_multi");
  });

  it("falls back to free text for anything else unrecognised", () => {
    expect(coerceSectionType("wingdings")).toBe(SAFE_SECTION_TYPE);
    expect(coerceSectionType("")).toBe(SAFE_SECTION_TYPE);
    expect(coerceSectionType(undefined)).toBe(SAFE_SECTION_TYPE);
  });

  it("leaves a recognised type alone", () => {
    for (const type of SECTION_TYPES) {
      expect(coerceSectionType(type)).toBe(type);
    }
  });
});

describe("coerceLoadedSections", () => {
  it("repairs a section that arrived from the server with checkbox", () => {
    const [section] = coerceLoadedSections([serverSection("checkbox")]);
    expect(section.section_type).toBe("checkbox_multi");
  });

  it("keeps every other field untouched", () => {
    const input = serverSection("checkbox");
    const [section] = coerceLoadedSections([input]);
    expect({ ...section, section_type: input.section_type }).toEqual(input);
  });

  it("tolerates an empty list", () => {
    expect(coerceLoadedSections([])).toEqual([]);
  });
});

describe("ingest points are guarded", () => {
  it("a schema loaded by fingerprint is coerced before it reaches state", () => {
    expect(TEACH_SRC).toMatch(/coerceLoadedSections\(/);
  });

  it("an LLM detect response is coerced before it reaches state", () => {
    expect(HOOK_SRC).toMatch(/coerceLoadedSections\(/);
  });
});
