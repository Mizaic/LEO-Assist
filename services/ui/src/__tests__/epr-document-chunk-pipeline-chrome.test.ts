/**
 * Static VT: document chunk pipeline runner in Care Documents tab.
 */
import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("EPR document chunk pipeline chrome", () => {
  test("DocumentChunkPanel loads chunks and starts document runs", () => {
    const panel = readUi("components/patients/DocumentChunkPanel.tsx");
    const api = readUi("lib/documentRunApi.ts");
    expect(panel).toMatch(/listResolvedDocumentReferenceChunks/);
    expect(panel).toMatch(/startDocumentRun/);
    expect(panel).toMatch(/pollDocumentRunUntilTerminal/);
    expect(panel).toMatch(/Run pipeline on selected chunks/);
    expect(panel).toMatch(/document-reprocess-dialog/);
    expect(panel).toMatch(/Reprocess document/);
    expect(api).toMatch(/\/document-runs/);
    expect(api).toMatch(/llm_usage/);
  });

  test("Care document reprocess uses the Validation Lab run sheet", () => {
    const panel = readUi("components/patients/DocumentChunkPanel.tsx");
    const sheet = readUi("app/admin/validation-lab/RunSheetDialog.tsx");
    expect(panel).toMatch(/RunSheetDialog/);
    expect(panel).toMatch(/sheetFromDocumentRun/);
    expect(panel).not.toMatch(/function RunProgressDialog/);
    expect(sheet).toMatch(/ProgressStrip/);
    expect(sheet).toMatch(/TaskList/);
  });

  test("Care reprocess does not open an SBAR drawer from the run sheet", () => {
    const panel = readUi("components/patients/DocumentChunkPanel.tsx");
    const sheet = readUi("app/admin/validation-lab/RunSheetDialog.tsx");
    expect(panel).toMatch(/showSbarActions=\{false\}/);
    expect(panel).not.toMatch(/RunSheetSbarActions/);
    expect(sheet).toMatch(/showSbarActions/);
  });

  test("Care reprocess refreshes the document list when the run sheet is dismissed", () => {
    const panel = readUi("components/patients/DocumentChunkPanel.tsx");
    const viewer = readUi("components/patients/DocumentViewer.tsx");
    const list = readUi("components/patients/DocumentListPanel.tsx");
    expect(viewer).toMatch(/onDocumentsChanged=\{onDocumentsChanged\}/);
    expect(panel).toMatch(/onDocumentsChanged\?/);
    expect(panel).toMatch(/assessment:/);
    expect(list).toMatch(/preferredId/);
  });

  test("DocumentViewer renders linked SBAR on referral documents", () => {
    const src = readUi("components/patients/DocumentViewer.tsx");
    expect(src).toMatch(/hasLinkedSbarAssessment/);
    expect(src).toMatch(/document-linked-sbar/);
    expect(src).toMatch(/showDocumentBody/);
    expect(src).toMatch(/document-sbar-widget/);
    expect(src).toMatch(/document-reprocess-button/);
    expect(src).toMatch(/patientDocumentFileUrl/);
    expect(src).toMatch(/inlineFileUrl/);
    expect(src).toMatch(/document-inline-pdf/);
  });
});
