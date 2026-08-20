/**
 * Helpers for inferring clinical document file type and source filename.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
import type { AssessmentRow, DocumentRow } from "@/lib/patientEprApi";

export type DocumentFileKind = "pdf" | "word" | "html" | "markdown" | "letter" | "unknown";

const DOC_HEADER_RE = /^--- Document:\s*(.+?)\s*---/m;
const DOC_HEADER_LINE_RE = /^--- Document:\s*.+?\s*---\s*\n?/m;

export function extractSourceFilename(text: string): string | null {
  const match = text.match(DOC_HEADER_RE);
  return match?.[1]?.trim() ?? null;
}

export function stripDocumentHeader(text: string): string {
  return String(text || "").replace(DOC_HEADER_LINE_RE, "").trim();
}

export function inferFileKind(doc: DocumentRow): DocumentFileKind {
  const ct = (doc.content_type ?? "").toLowerCase();
  if (ct.includes("pdf")) return "pdf";
  if (
    ct.includes("word") ||
    ct.includes("docx") ||
    ct.includes("msword") ||
    ct.includes("wordprocessingml")
  ) {
    return "word";
  }
  if (ct.includes("markdown") || ct.includes("text/markdown")) return "markdown";
  if (ct.includes("html")) return "html";

  const title = doc.title.toLowerCase();
  if (title.endsWith(".pdf")) return "pdf";
  if (title.endsWith(".docx") || title.endsWith(".doc")) return "word";
  if (title.endsWith(".html") || title.endsWith(".htm")) return "html";

  const fileUrl = (doc.original_url || doc.markdown_url || "").toLowerCase();
  const filePath = fileUrl.split("?", 1)[0] ?? "";
  if (filePath.endsWith(".pdf")) return "pdf";
  if (filePath.includes("wordprocessingml.document") || filePath.endsWith(".docx")) {
    return "word";
  }
  if (filePath.endsWith(".doc")) return "word";
  if (filePath.endsWith(".html") || filePath.endsWith(".htm")) return "html";

  const source = extractSourceFilename(doc.full_text)?.toLowerCase() ?? "";
  if (source.endsWith(".pdf")) return "pdf";
  if (source.endsWith(".docx") || source.endsWith(".doc")) return "word";
  if (source.endsWith(".html") || source.endsWith(".htm")) return "html";

  const dtype = doc.document_type.toLowerCase();
  if (
    dtype.includes("letter") ||
    dtype.includes("referral") ||
    dtype.includes("summary") ||
    dtype.includes("clinic")
  ) {
    return "letter";
  }

  if (doc.full_text.includes("| --- |") || doc.full_text.startsWith("Dear ")) {
    return "letter";
  }

  return doc.full_text ? "markdown" : "unknown";
}

export function isWordDocumentRow(doc: DocumentRow): boolean {
  return inferFileKind(doc) === "word";
}

export function isHtmlDocumentRow(doc: DocumentRow): boolean {
  return inferFileKind(doc) === "html";
}

export function looksLikeHtmlBody(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return trimmed.startsWith("<") || /<html[\s>]/i.test(trimmed) || /<body[\s>]/i.test(trimmed);
}

export function fileKindLabel(kind: DocumentFileKind): string {
  switch (kind) {
    case "pdf":
      return "PDF";
    case "word":
      return "Word";
    case "html":
      return "HTML";
    case "markdown":
      return "Markdown";
    case "letter":
      return "Letter";
    default:
      return "Document";
  }
}

export function categoryLabel(category: string | null): string {
  if (!category) return "";
  return category.replace(/_/g, " ");
}

export function isSbarDocument(doc: DocumentRow): boolean {
  const type = doc.document_type.toLowerCase();
  const category = (doc.category ?? "").toLowerCase();
  return type.includes("sbar") || category === "sbar";
}

export function hasLinkedSbarAssessment(doc: DocumentRow): boolean {
  return Boolean(doc.sbar?.sbar_id?.trim());
}

/** Map a patient Assessment into a Documents-tab row (SBAR). */
export function assessmentToDocumentRow(row: AssessmentRow): DocumentRow {
  const preview =
    row.situation ||
    row.content ||
    "Clinical SBAR summary";
  return {
    document_id: `assessment:${row.assessment_id}`,
    document_date: row.created_at,
    document_type: "SBAR",
    title: `SBAR -- ${row.episode_label || "Patient summary"}`,
    category: "sbar",
    text_preview: preview.slice(0, 200),
    full_text: row.content || "",
    content_type: null,
    original_url: null,
    markdown_url: null,
    episode_id: row.episode_id,
    episode_label: row.episode_label || "General",
    folder_label: row.episode_label || "General",
    referral_id: null,
    chunk_count: 0,
    sbar: {
      sbar_id: row.assessment_id,
      status: row.status,
      situation: row.situation,
      background: row.background,
      assessment: row.assessment,
      recommendation: row.recommendation,
    },
  };
}

/** Merge DocumentReferences with Assessment SBARs; newest first. */
export function mergeDocumentsNewestFirst(
  docs: DocumentRow[],
  assessments: AssessmentRow[],
): DocumentRow[] {
  const existingSbarIds = new Set(
    docs
      .filter((d) => isSbarDocument(d) && d.sbar?.sbar_id)
      .map((d) => d.sbar!.sbar_id),
  );
  const sbarDocs = assessments
    .filter((a) => a.assessment_id && !existingSbarIds.has(a.assessment_id))
    .map(assessmentToDocumentRow);
  return [...docs, ...sbarDocs].sort((a, b) => {
    const ta = a.document_date ? Date.parse(a.document_date) : 0;
    const tb = b.document_date ? Date.parse(b.document_date) : 0;
    return tb - ta;
  });
}
