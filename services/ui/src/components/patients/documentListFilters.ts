/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
import type { DocumentRow } from "@/lib/patientEprApi";
import { isSbarDocument } from "./documentFormat";

export const TYPE_FILTER_OPTIONS = [
  { id: "all", label: "All types" },
  { id: "referral", label: "Referrals" },
  { id: "letter", label: "Letters" },
  { id: "summary", label: "Summaries" },
  { id: "sbar", label: "SBARs" },
] as const;

export type DocumentTypeFilter = (typeof TYPE_FILTER_OPTIONS)[number]["id"];

export function documentFolderKey(doc: DocumentRow): string {
  return doc.folder_label ?? doc.episode_label ?? "General";
}

export function matchesTypeFilter(doc: DocumentRow, filter: DocumentTypeFilter): boolean {
  if (filter === "all") return true;
  const t = doc.document_type.toLowerCase();
  const title = doc.title.toLowerCase();
  const cat = (doc.category ?? "").toLowerCase();
  if (filter === "sbar") return isSbarDocument(doc);
  if (filter === "referral") {
    return (
      t.includes("referral") ||
      title.includes("referral") ||
      cat.includes("referral") ||
      title.includes("clinical information") ||
      title.includes("2ww") ||
      title.includes("form v")
    );
  }
  if (filter === "letter") {
    if (isSbarDocument(doc)) return false;
    return (
      t.includes("letter") ||
      t.includes("clinic") ||
      t.includes("document") ||
      cat.includes("letter") ||
      Boolean(doc.text_preview?.trim().toLowerCase().startsWith("dear "))
    );
  }
  if (filter === "summary") {
    return t.includes("summary") || t.includes("discharge") || cat.includes("summary");
  }
  return true;
}

export function sortFolderLabels(labels: string[]): string[] {
  return [...labels].sort((a, b) => {
    if (a === "General") return 1;
    if (b === "General") return -1;
    return a.localeCompare(b);
  });
}

export function folderCounts(docs: DocumentRow[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const doc of docs) {
    const key = documentFolderKey(doc);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}
