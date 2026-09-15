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
    const toolbar = readUi("components/patients/DocumentWorkspaceToolbar.tsx");
    expect(src).toMatch(/fetchEprAssessments/);
    expect(src).toMatch(/mergeDocumentsNewestFirst/);
    expect(src).toMatch(/documentFolderKey/);
    expect(src).toMatch(/DocumentFolderBlock/);
    expect(toolbar).toMatch(/Specialty/);
    expect(src).toMatch(/Expand all/);
    expect(src).toMatch(/initialDocumentId/);
    expect(src).toMatch(/initialReferralId/);
    const filters = readUi("components/patients/documentListFilters.ts");
    expect(filters).toMatch(/clinical information/);
    expect(filters).toMatch(/2ww/);
  });

  test("Document workspace fills the tab and keeps journey builder collapsed", () => {
    const panel = readUi("components/patients/DocumentListPanel.tsx");
    const toolbar = readUi("components/patients/DocumentWorkspaceToolbar.tsx");
    const builder = readUi("components/patients/JourneyBuilderPanel.tsx");
    expect(panel).toMatch(/epr-document-workspace/);
    expect(toolbar).toMatch(/FilterBar/);
    expect(panel).not.toMatch(/100vh/);
    expect(builder).toMatch(/ProgressiveReveal/);
    expect(builder).toMatch(/Build a journey/);
    expect(builder).toMatch(/defaultOpen=\{false\}/);
  });

  test("DocumentViewer renders markdown inline or embeds PDF and Word preview", () => {
    const src = readUi("components/patients/DocumentViewer.tsx");
    const word = readUi("components/patients/DocumentWordPreviewPane.tsx");
    const html = readUi("components/patients/DocumentHtmlPreviewPane.tsx");
    const fmt = readUi("components/patients/documentFormat.ts");
    const api = readUi("lib/patientEprApi.ts");
    expect(src).toMatch(/MarkdownEditor/);
    expect(src).toMatch(/InlinePdfPane/);
    expect(src).toMatch(/DocumentWordPreviewPane/);
    expect(src).toMatch(/DocumentHtmlPreviewPane/);
    expect(src).toMatch(/showHtmlPreview/);
    expect(fmt).toMatch(/wordprocessingml/);
    expect(fmt).toMatch(/isHtmlDocumentRow/);
    expect(html).toMatch(/srcDoc/);
    expect(html).toMatch(/DOMPurify\.sanitize/);
    expect(html).toMatch(/wrapClinicalPreviewHtml/);
    expect(readUi("components/patients/clinicalPreviewDocument.ts")).toMatch(/CLINICAL_PREVIEW_CSS/);
    expect(word).toMatch(/fetchDocumentPreview/);
    expect(word).toMatch(/DOMPurify\.sanitize/);
    expect(api).toMatch(/fetchDocumentPreview/);
  });

  test("documentFormat exposes merge helper and SBAR type guard", () => {
    const src = readUi("components/patients/documentFormat.ts");
    expect(src).toMatch(/export function isSbarDocument/);
    expect(src).toMatch(/export function mergeDocumentsNewestFirst/);
    expect(src).toMatch(/document_type: "SBAR"/);
    expect(src).toMatch(/chunk_count: 0/);
  });

  test("DocumentListItem shows AI ready chip when chunks exist", () => {
    const item = readUi("components/patients/DocumentListItem.tsx");
    const chip = readUi("components/patients/DocumentAiReadyChip.tsx");
    const api = readUi("lib/patientEprApi.ts");
    expect(item).toMatch(/DocumentAiReadyChip/);
    expect(item).toMatch(/chunk_count/);
    expect(chip).toMatch(/AI ready/);
    expect(chip).toMatch(/document-ai-ready-chip/);
    expect(api).toMatch(/chunk_count/);
  });
});
