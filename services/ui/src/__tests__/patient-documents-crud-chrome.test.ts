/**
 * VT - patient documents CRUD chrome.
 *
 * Static-source verification for journey document CRUD UI.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("patient documents CRUD chrome", () => {
  test("TC-001: DocumentListPanel exposes add document control", () => {
    const src = readFile("services/ui/src/components/patients/DocumentListPanel.tsx");
    expect(src).toMatch(/add-document-button/);
    expect(src).toMatch(/DocumentEditorDialog/);
    expect(src).toMatch(/JourneyBuilderPanel/);
  });

  test("TC-002: DocumentViewer wires edit and delete with ConfirmDialog", () => {
    const src = readFile("services/ui/src/components/patients/DocumentViewer.tsx");
    expect(src).toMatch(/edit-document-button/);
    expect(src).toMatch(/delete-document-button/);
    expect(src).toMatch(/ConfirmDialog/);
    expect(src).toMatch(/deletePatientDocument/);
  });

  test("TC-003: patientDocumentsApi calls core patient document routes", () => {
    const src = readFile("services/ui/src/lib/patientDocumentsApi.ts");
    expect(src).toMatch(/\/api\/patients\//);
    expect(src).toMatch(/milestone-sbar/);
  });
});
