/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Right-column stand-in for `LivePreviewPane` while the guided
 * highlight-to-build wizard is still working through its own steps
 * (prerequisites / pathway split / pathway conditions).
 *
 * Before Review, "what this rule means" is either empty or only
 * half-built, so a live summary there is more confusing than useful.
 * What IS useful the whole way through is the guideline sentence
 * itself, pinned here instead of living at the top of a canvas the
 * reviewer has to scroll back up to re-read on every step. Once the
 * wizard reaches Review, the host swaps back to `LivePreviewPane`,
 * which is finally showing a tree worth previewing.
 *
 * Pure presentational, same sticky right-column contract as
 * `LivePreviewPane`. When `tree` is supplied, every leaf that already
 * anchors onto `recommendationText` (via `collectTreeHighlights`) is
 * highlighted in place -- the same green used for a "confirmed" match
 * everywhere else in this wizard -- so a reviewer can see at a glance
 * which words they have already turned into rule conditions, without
 * re-reading the whole paragraph on every step.
 */

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MenuBookRoundedIcon from "@mui/icons-material/MenuBookRounded";

import { collectTreeHighlights } from "./HighlightWizard/leafTextMatch";
import {
  HIGHLIGHT_COLORS,
  type HighlightSpan,
} from "./SentenceEditor/HighlightableRecommendationText";
import type { EditableLogicNode } from "./types";

interface Props {
  recommendationText?: string | null;
  /** Current rule tree -- when present, its leaves' matching words are
   *  highlighted in the quote below. Omit (or pass null) to render the
   *  quote plain, e.g. before any tree exists yet. */
  tree?: EditableLogicNode | null;
}

/** Merges overlapping/adjacent highlight spans and sorts them, so the
 * renderer below can do one straight left-to-right pass over `text`
 * instead of re-checking every span against every character. Exported
 * for direct unit testing of the merge logic on its own. */
export function mergeHighlightRanges(
  highlights: HighlightSpan[],
): Array<{ start: number; end: number }> {
  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const merged: Array<{ start: number; end: number }> = [];
  for (const span of sorted) {
    const last = merged[merged.length - 1];
    if (last && span.start <= last.end) {
      last.end = Math.max(last.end, span.end);
    } else {
      merged.push({ start: span.start, end: span.end });
    }
  }
  return merged;
}

/** Renders `text` as plain runs interleaved with `<mark>` runs for
 * each merged highlight range -- read-only, no word tokenisation or
 * interaction handlers, since this quote is reference-only. */
function renderHighlightedQuote(
  text: string,
  highlights: HighlightSpan[],
): React.ReactNode {
  const ranges = mergeHighlightRanges(highlights);
  if (ranges.length === 0) return text;

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((range, i) => {
    if (range.start > cursor) {
      nodes.push(<span key={`plain-${i}`}>{text.slice(cursor, range.start)}</span>);
    }
    nodes.push(
      <Box
        key={`mark-${i}`}
        component="mark"
        sx={{
          bgcolor: HIGHLIGHT_COLORS.confirmed.bgcolor,
          color: HIGHLIGHT_COLORS.confirmed.color,
          borderRadius: 0.5,
          px: "1px",
        }}
      >
        {text.slice(range.start, range.end)}
      </Box>,
    );
    cursor = range.end;
  });
  if (cursor < text.length) {
    nodes.push(<span key="plain-end">{text.slice(cursor)}</span>);
  }
  return nodes;
}

export default function GuidelineQuotePanel({ recommendationText, tree }: Props) {
  const highlights = useMemo(
    () => collectTreeHighlights(recommendationText, tree),
    [recommendationText, tree],
  );

  return (
    <Box
      role="region"
      aria-label="NICE guideline wording for this rule"
      sx={{
        position: "sticky",
        top: 0,
        alignSelf: "flex-start",
        p: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.75}>
        <MenuBookRoundedIcon sx={{ fontSize: 16, color: "primary.main" }} />
        <Typography
          variant="overline"
          sx={{
            display: "block",
            color: "text.secondary",
            letterSpacing: 0.5,
            lineHeight: 1,
          }}
        >
          NICE recommendation
        </Typography>
      </Stack>
      {recommendationText ? (
        <Box
          sx={{
            p: 1.5,
            borderLeft: "4px solid",
            borderColor: "primary.main",
            bgcolor: "background.paper",
            borderRadius: "0 8px 8px 0",
          }}
        >
          <Typography
            variant="body2"
            sx={{ fontStyle: "italic", lineHeight: 1.6, color: "text.primary" }}
          >
            {renderHighlightedQuote(recommendationText, highlights)}
          </Typography>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          This rule has no guideline text to show.
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.5 }}>
        {highlights.length > 0
          ? "Highlighted words are already captured on the left. Check the rest against what's still missing."
          : "Keep checking this against what you pick on the left. You'll see the full rule summary once you reach Review."}
      </Typography>
    </Box>
  );
}
