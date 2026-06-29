/**
 * Helpers for inferring clinical document file type and source filename.
 */
import type { DocumentRow } from "@/lib/patientEprApi";

export type DocumentFileKind = "pdf" | "word" | "markdown" | "letter" | "unknown";

const DOC_HEADER_RE = /^--- Document:\s*(.+?)\s*---/m;

export function extractSourceFilename(text: string): string | null {
  const match = text.match(DOC_HEADER_RE);
  return match?.[1]?.trim() ?? null;
}

export function inferFileKind(doc: DocumentRow): DocumentFileKind {
  const ct = (doc.content_type ?? "").toLowerCase();
  if (ct.includes("pdf")) return "pdf";
  if (ct.includes("word") || ct.includes("docx") || ct.includes("msword")) {
    return "word";
  }
  if (ct.includes("markdown") || ct.includes("text/markdown")) return "markdown";

  const title = doc.title.toLowerCase();
  if (title.endsWith(".pdf")) return "pdf";
  if (title.endsWith(".docx") || title.endsWith(".doc")) return "word";

  const source = extractSourceFilename(doc.full_text)?.toLowerCase() ?? "";
  if (source.endsWith(".pdf")) return "pdf";
  if (source.endsWith(".docx") || source.endsWith(".doc")) return "word";

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

export function fileKindLabel(kind: DocumentFileKind): string {
  switch (kind) {
    case "pdf":
      return "PDF";
    case "word":
      return "Word";
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
