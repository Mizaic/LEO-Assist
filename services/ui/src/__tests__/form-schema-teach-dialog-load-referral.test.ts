/**
 * Static-source VT for the "Load from referral" feature in FormSchemaTeachDialog.
 *
 * Asserts that:
 * - The UBRN input field is present.
 * - The Load button is present.
 * - fetchLetterTextByUbrn is imported from formSchemaApi.
 * - The error alert data-testid is present.
 * - formSchemaApi exports the fetchLetterTextByUbrn and LetterTextResult types.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

import * as fs from "fs";
import * as path from "path";

const SETTINGS_SCHEMAS = path.join(
  __dirname,
  "../app/settings/form-schemas",
);

const DIALOG_SRC = fs.readFileSync(
  path.join(SETTINGS_SCHEMAS, "FormSchemaTeachDialog.tsx"),
  "utf8",
);

const API_SRC = fs.readFileSync(
  path.join(SETTINGS_SCHEMAS, "formSchemaApi.ts"),
  "utf8",
);

describe("FormSchemaTeachDialog - Load from referral", () => {
  it("imports fetchLetterTextByUbrn from formSchemaApi", () => {
    expect(DIALOG_SRC).toContain("fetchLetterTextByUbrn");
    expect(DIALOG_SRC).toContain("./formSchemaApi");
  });

  it("renders a UBRN text field", () => {
    expect(DIALOG_SRC).toContain("load-from-referral-row");
    expect(DIALOG_SRC).toContain("aria-label");
    expect(DIALOG_SRC).toContain("UBRN");
  });

  it("renders a Load button", () => {
    expect(DIALOG_SRC).toContain("load-from-referral-btn");
    expect(DIALOG_SRC).toContain("Load");
  });

  it("shows an error alert when the referral is not found", () => {
    expect(DIALOG_SRC).toContain("ubrn-error");
    expect(DIALOG_SRC).toContain("ubrnError");
  });

  it("clears state on close", () => {
    expect(DIALOG_SRC).toContain("setUbrnInput");
    expect(DIALOG_SRC).toContain("setUbrnError");
  });
});

describe("FormSchemaTeachDialog - Edit skips letter step", () => {
  it("loads the saved schema by fingerprint on open", () => {
    expect(DIALOG_SRC).toMatch(/fetchFormSchema/);
    expect(API_SRC).toMatch(/export async function fetchFormSchema/);
    expect(API_SRC).toMatch(/\/api\/form-schemas\/\$\{/);
  });

  it("does not gate the schema editor on letter text alone", () => {
    expect(DIALOG_SRC).not.toMatch(/canTeach && ready/);
    expect(DIALOG_SRC).not.toMatch(/disabled=\{!canTeach\}/);
  });

  it("opens the editor when saved sections exist", () => {
    expect(DIALOG_SRC).toMatch(/sections\.length|savedHasSections|hasSavedSections/);
    expect(DIALOG_SRC).toMatch(/setReady\(\s*true\s*\)/);
  });

  it("says the letter box is needed to save changes", () => {
    expect(DIALOG_SRC).toMatch(/You need it to save\s+changes/);
    expect(DIALOG_SRC).not.toMatch(/without one/);
    expect(DIALOG_SRC).toContain("Sample referral letter");
    expect(DIALOG_SRC).toContain("load-from-referral-row");
  });
});

describe("formSchemaApi - fetchLetterTextByUbrn", () => {
  it("exports fetchLetterTextByUbrn function", () => {
    expect(API_SRC).toContain("export async function fetchLetterTextByUbrn");
  });

  it("exports LetterTextResult interface", () => {
    expect(API_SRC).toContain("export interface LetterTextResult");
    expect(API_SRC).toContain("text: string");
    expect(API_SRC).toContain("fingerprint: string");
    expect(API_SRC).toContain("chunk_count: number");
  });

  it("calls the correct API endpoint", () => {
    expect(API_SRC).toContain("/api/form-schemas/letter-text");
    expect(API_SRC).toContain("organization_id");
  });
});
