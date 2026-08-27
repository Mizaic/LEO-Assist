/**
 * VT: "Add standard blood panel" loads the NHS preset into ordered_tests.
 *
 * Verifies:
 *   - The preset loader calls the guarded form-schemas preset route.
 *   - Preset rows map onto FormSchemaItem with procedure + analyte codes.
 *   - Merging skips batteries the section already has, so a second click
 *     does not duplicate rows.
 *   - The button reports a plain-English error when the load fails.
 *   - The ordered_tests editor renders the action and appends via onPatch.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

import * as fs from "fs";
import * as path from "path";

import {
  fetchBloodPanelPreset,
  mergePresetBatteries,
} from "../components/operations/bloodPanelPresets";
import type { FormSchemaItem } from "../components/operations/formSchemaDetector";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readSource(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const PRESET_RESPONSE = {
  batteries: [
    {
      pattern: "FBC",
      entity_text: "Complete blood count",
      semantic_tag: "procedure",
      assertion: "present",
      procedure_snomed: "26604007",
      procedure_display: "Complete blood count",
      analytes: [
        { label: "Hb", snomed_code: "1022431000000105", display: "Haemoglobin" },
        { label: "WCC", snomed_code: "1110441000000100", display: "White cells" },
      ],
      value_placeholder: "",
    },
    {
      pattern: "UE",
      entity_text: "Measurement of urea and electrolytes",
      semantic_tag: "procedure",
      assertion: "present",
      procedure_snomed: "252167001",
      procedure_display: "Measurement of urea and electrolytes",
      analytes: [
        { label: "Na", snomed_code: "1000661000000107", display: "Sodium" },
      ],
      value_placeholder: "",
    },
  ],
  needs_clinical_review: { Iron: "No panel concept exists." },
};

describe("bloodPanelPresets loader", () => {
  beforeEach(() => {
    global.fetch = jest.fn() as unknown as typeof fetch;
  });

  it("calls the guarded preset route and maps rows to form schema items", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(PRESET_RESPONSE),
    });

    const items = await fetchBloodPanelPreset();

    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe("/api/form-schemas/blood-panel-presets");
    expect(init.credentials).toBe("include");
    expect(items).toHaveLength(2);
    expect(items[0].pattern).toBe("FBC");
    expect(items[0].procedure_snomed).toBe("26604007");
    expect(items[0].semantic_tag).toBe("procedure");
    expect(items[0].analytes).toHaveLength(2);
    expect(items[0].analytes?.[0].snomed_code).toBe("1022431000000105");
  });

  it("throws a plain-English error when the route fails", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 500 });
    await expect(fetchBloodPanelPreset()).rejects.toThrow(
      "We could not load the standard blood panel. Try again.",
    );
  });
});

describe("mergePresetBatteries", () => {
  const preset: FormSchemaItem[] = [
    {
      pattern: "FBC",
      entity_text: "Complete blood count",
      semantic_tag: "procedure",
      assertion: "present",
      analytes: [],
    },
    {
      pattern: "UE",
      entity_text: "Measurement of urea and electrolytes",
      semantic_tag: "procedure",
      assertion: "present",
      analytes: [],
    },
  ];

  it("appends every battery to an empty section", () => {
    expect(mergePresetBatteries([], preset).map((i) => i.pattern)).toEqual([
      "FBC",
      "UE",
    ]);
  });

  it("keeps existing rows and skips batteries already present", () => {
    const existing: FormSchemaItem[] = [
      {
        pattern: "fbc",
        entity_text: "My own FBC row",
        semantic_tag: "procedure",
        assertion: "present",
      },
    ];
    const merged = mergePresetBatteries(existing, preset);
    expect(merged.map((i) => i.pattern)).toEqual(["fbc", "UE"]);
    expect(merged[0].entity_text).toBe("My own FBC row");
  });

  it("drops blank placeholder rows so the preset is not padded", () => {
    const existing: FormSchemaItem[] = [
      { pattern: "", entity_text: "", semantic_tag: "procedure", assertion: "present" },
    ];
    expect(mergePresetBatteries(existing, preset).map((i) => i.pattern)).toEqual([
      "FBC",
      "UE",
    ]);
  });
});

describe("ordered_tests editor wiring", () => {
  const editor = readSource(
    "services/ui/src/components/operations/FormSchemaSectionEditor.tsx",
  );
  const button = readSource(
    "services/ui/src/components/operations/BloodPanelPresetButton.tsx",
  );

  it("renders the preset action inside the ordered_tests branch", () => {
    expect(editor).toMatch(/BloodPanelPresetButton/);
    const branch = editor.match(
      /section\.section_type === "ordered_tests" \?[\s\S]*?\) : \(/,
    );
    expect(branch?.[0]).toMatch(/BloodPanelPresetButton/);
  });

  it("appends preset rows through the existing section patch handler", () => {
    expect(editor).toMatch(/mergePresetBatteries\(\s*section\.items,\s*items\s*\)/);
    expect(editor).toMatch(/onPatch\(\{\s*items:\s*mergePresetBatteries/);
  });

  it("labels the action in plain English and keeps it accessible", () => {
    expect(button).toMatch(/Add standard blood panel/);
    expect(button).toMatch(/aria-live="polite"/);
    expect(button).toMatch(/disabled=\{loading\}/);
  });

  it("does not duplicate SnomedLookupField", () => {
    expect(button).not.toMatch(/Autocomplete/);
    expect(button).not.toMatch(/searchTerms/);
  });
});
