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
    expect(panel).toMatch(/LeoSbarHost/);
    expect(panel).toMatch(/platform admins/);
    expect(api).toMatch(/\/document-runs/);
  });

  test("DocumentViewer renders linked SBAR on referral documents", () => {
    const src = readUi("components/patients/DocumentViewer.tsx");
    expect(src).toMatch(/hasLinkedSbarAssessment/);
    expect(src).toMatch(/document-linked-sbar/);
    expect(src).toMatch(/showDocumentBody/);
    expect(src).toMatch(/document-sbar-widget/);
    expect(src).toMatch(/DocumentChunkPanel/);
    expect(src).toMatch(/document-sbar-reprocess-hint/);
  });
});
