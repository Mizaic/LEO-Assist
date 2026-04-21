/**
 * SBAR markdown splitter.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (one source tree, two variants render the same)
 *
 * Mirrors libs equivalents and services/ui splitFinalSbar so the
 * widget renders sections in the same canonical order regardless of
 * which Mizaic-portfolio host embeds it.
 */

import type { SbarSection, SbarStageName } from "../data/types";

const SECTION_ORDER: SbarStageName[] = [
  "situation",
  "background",
  "assessment",
  "recommendation",
];

const SECTION_SET: ReadonlySet<string> = new Set(SECTION_ORDER);

const HEADING_RE = /^##\s+(.+?)\s*$/;
const SOURCE_COMMENT_LINE_RE =
  /^[ \t]*<!--\s*sources:\s*[^>]*?-->[ \t]*\r?\n?/gm;
const SOURCE_COMMENT_INLINE_RE = /<!--\s*sources:\s*[^>]*?-->/g;

export function stripSourceComments(md: string): string {
  if (!md) return md;
  return md
    .replace(SOURCE_COMMENT_LINE_RE, "")
    .replace(SOURCE_COMMENT_INLINE_RE, "");
}

export function splitFinalSbar(md: string): SbarSection[] {
  const lines = (md ?? "").split(/\r?\n/);
  const out = new Map<SbarStageName, string[]>();
  let current: SbarStageName | null = null;
  for (const line of lines) {
    const heading = HEADING_RE.exec(line);
    if (heading && heading[1]) {
      const name = heading[1].trim().toLowerCase();
      if (SECTION_SET.has(name)) {
        current = name as SbarStageName;
        if (!out.has(current)) out.set(current, []);
        continue;
      }
      current = null;
      continue;
    }
    if (current) out.get(current)!.push(line);
  }
  return SECTION_ORDER.filter((s) => out.has(s)).map((stage) => ({
    stage,
    body: (out.get(stage) ?? []).join("\n").trim(),
  }));
}
