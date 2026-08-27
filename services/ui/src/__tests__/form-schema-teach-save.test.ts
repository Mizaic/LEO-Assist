/**
 * VT: ordered_tests batteries must survive prepareSectionsForSave.
 *
 * Atlas trace: DI-5C9CA57B
 */
import { prepareSectionsForSave } from "../components/operations/formSchemaTeach";
import type { FormSchemaSection } from "../components/operations/formSchemaDetector";

describe("prepareSectionsForSave ordered_tests round-trip", () => {
  it("keeps blood batteries with analytes when entity_text is empty", () => {
    const sections: FormSchemaSection[] = [
      {
        section_id: "S1",
        section_type: "ordered_tests",
        label: "Blood Tests",
        start_pattern: "Blood Tests",
        semantic_tags: ["procedure"],
        items: [
          {
            pattern: "FBC",
            entity_text: "",
            semantic_tag: "procedure",
            assertion: "present",
            procedure_snomed: "26604007",
            procedure_display: "Full blood count",
            analytes: [
              {
                label: "Hb",
                snomed_code: "1022280009",
                display: "Haemoglobin",
              },
            ],
          },
        ],
      },
    ];

    const saved = prepareSectionsForSave(sections);
    expect(saved).toHaveLength(1);
    expect(saved[0].items).toHaveLength(1);
    expect(saved[0].items[0].pattern).toBe("FBC");
    expect(saved[0].items[0].entity_text).toBe("Full blood count");
    expect(saved[0].items[0].analytes).toHaveLength(1);
  });
});
