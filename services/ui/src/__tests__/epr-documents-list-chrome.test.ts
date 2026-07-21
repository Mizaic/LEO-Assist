/**
 * Static VT: EPR Documents tab shows letters and SBARs, newest first.
 *
 * Atlas: DI-357A7468 / DO-5D3EA371
 */
import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("EPR documents list chrome", () => {
  test("DocumentViewer does not treat linked Assessment as document type SBAR", () => {
    const src = readUi("components/patients/DocumentViewer.tsx");
    expect(src).toMatch(/isSbarDocument/);
    expect(src).not.toMatch(/Boolean\(doc\.sbar\)/);
  });

  test("DocumentListPanel merges assessments and sorts newest first", () => {
    const src = readUi("components/patients/DocumentListPanel.tsx");
    expect(src).toMatch(/fetchEprAssessments/);
    expect(src).toMatch(/mergeDocumentsNewestFirst/);
  });

  test("documentFormat exposes merge helper and SBAR type guard", () => {
    const src = readUi("components/patients/documentFormat.ts");
    expect(src).toMatch(/export function isSbarDocument/);
    expect(src).toMatch(/export function mergeDocumentsNewestFirst/);
    expect(src).toMatch(/document_type: "SBAR"/);
  });
});
