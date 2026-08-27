/**
 * Map UI shorthand semantic tags to terminology search filters.
 *
 * Atlas trace: DI-5C9CA57B
 */

/** Canonical tag for terminology /api/terminology/search semantic_tag param. */
export function normaliseTerminologyLookupTag(raw: string): string {
  const tag = String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s/-]+/g, "_");
  if (!tag) return "";
  if (tag === "observable" || tag === "observation") return "observable_entity";
  if (tag === "observable_entity") return "observable_entity";
  return tag;
}

export function normaliseTerminologyLookupTags(tags: string[]): string[] {
  const out = new Set<string>();
  for (const raw of tags) {
    const tag = normaliseTerminologyLookupTag(raw);
    if (tag) out.add(tag);
  }
  return [...out];
}
