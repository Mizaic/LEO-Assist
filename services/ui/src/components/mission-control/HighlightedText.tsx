/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

/**
 * HighlightedText -- shared search-term highlighter for the
 * encounter surfaces (DI-LEO-AI-514).
 *
 * One amber token, one regex, one set of helper rules used by:
 *   - EncounterPreviewDialog (the /care/encounters preview)
 *   - EncounterCard (the /care/patients side drawer text tab)
 *   - EncounterResultsTable (the /care/encounters search results)
 *
 * Centralising here removes the previous "fef3c7 vs fde68a" drift
 * between the dialog and the drawer and makes the highlight feel
 * identical wherever the reviewer sees it.
 */

import type { ReactNode } from "react";
import Box from "@mui/material/Box";

// Tokens shorter than this are skipped so a stray "a" or "in" from
// the user's query does not paint the entire encounter yellow.
export const MIN_HIGHLIGHT_LEN = 3;

// Amber token shared with the patient drawer's encounter cards.
export const HIGHLIGHT_BG = "#fde68a";

export function escapeRegex(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Collect the set of terms to highlight from the reviewer's free-
 * text query and an optional list of structured rationale terms
 * (typically `EncounterListItem.match_rationale`). Terms shorter
 * than {@link MIN_HIGHLIGHT_LEN} characters are dropped, duplicates
 * are removed (case-insensitive), and the result is sorted longest-
 * first so multi-word matches win over their substrings.
 */
export function collectHighlightTerms(
  searchQuery: string | undefined,
  rationale: string[] | undefined,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (raw: string) => {
    const t = raw.trim();
    if (t.length < MIN_HIGHLIGHT_LEN) return;
    const key = t.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(t);
  };
  // Split the user's query on whitespace + common punctuation so
  // "breast cancer screening" highlights all three words.
  if (searchQuery) {
    for (const tok of searchQuery.split(/[\s,.;:/()\[\]"']+/)) push(tok);
  }
  if (rationale) for (const tok of rationale) push(tok);
  // Match longer terms first so "cancer screening" wins over "cancer".
  out.sort((a, b) => b.length - a.length);
  return out;
}

interface HighlightedTextProps {
  text: string | null | undefined;
  terms: string[];
  /** Optional override for the test id on each <mark>. Defaults to
   *  "encounter-highlight" so the three consumers share the same
   *  hook in the static-source verification tests. */
  testId?: string;
}

/**
 * Wrap each case-insensitive occurrence of any term in {@link terms}
 * with `<Box component="mark">`. If `terms` is empty the text is
 * returned unchanged so callers do not need to guard the call.
 *
 * Callers SHOULD memoise `terms` (e.g. `useMemo`) to avoid
 * recompiling the regex on every render.
 */
export function HighlightedText({
  text,
  terms,
  testId = "encounter-highlight",
}: HighlightedTextProps): ReactNode {
  if (!text) return text ?? "";
  if (!terms.length) return text;
  const pattern = new RegExp(
    `(${terms.map(escapeRegex).join("|")})`,
    "gi",
  );
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, idx) => {
        if (!part) return null;
        // Even indices are non-matches, odd indices are captured hits
        // (because the pattern is a single capturing group).
        if (idx % 2 === 1) {
          return (
            <Box
              key={`hl-${idx}`}
              component="mark"
              data-testid={testId}
              sx={{
                bgcolor: HIGHLIGHT_BG,
                color: "inherit",
                px: 0.25,
                borderRadius: "2px",
                fontWeight: 600,
              }}
            >
              {part}
            </Box>
          );
        }
        return <span key={`hl-${idx}`}>{part}</span>;
      })}
    </>
  );
}
