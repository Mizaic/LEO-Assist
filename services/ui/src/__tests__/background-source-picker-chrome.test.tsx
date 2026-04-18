/**
 * VT-LEO-AI-232 -- BackgroundSourcePicker primitive (static-source layer)
 *
 * Pins the contracts of the patient-scoped picker (DI-LEO-AI-232 /
 * DO-LEO-AI-232):
 *   - exactly two top-level tabs (no third "chunks" tab)
 *   - chunks render inside the document Collapse, never as a tab
 *   - the picker calls the patient-scoped endpoints only
 */
import fs from "fs";
import path from "path";

const PRIMITIVE = path.resolve(
  __dirname,
  "..",
  "components",
  "sbar-playground",
  "BackgroundSourcePicker.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-232 BackgroundSourcePicker primitive", () => {
  it("declares exactly two tabs (Encounters, Letters and documents)", () => {
    const src = read(PRIMITIVE);
    const tabIds = src.match(/background-source-picker-tab-[a-z]+/g) ?? [];
    const unique = Array.from(new Set(tabIds)).sort();
    expect(unique).toEqual([
      "background-source-picker-tab-documents",
      "background-source-picker-tab-encounters",
    ]);
  });

  it("renders chunks inside a Collapse, not as a top-level tab", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/<Collapse[\s\S]*?<ChunkList/);
    // Sanity: no third tab.
    expect(src).not.toMatch(/background-source-picker-tab-chunks/);
  });

  it("loads chunks via listDocumentReferenceChunks for the parent DocumentReference", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/listDocumentReferenceChunks\(documentReferenceId/);
  });

  it("implements 'chunks drop parent' rule on confirm", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/docsWithChunks/);
    expect(src).toMatch(/if \(docsWithChunks\.has\(id\)\) continue/);
  });
});
