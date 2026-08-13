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
 * reviewer has to scroll back up to re-read on every step. The host
 * keeps this panel visible on Check / Suggest / Save as well, with
 * LivePreviewPane stacked underneath once the tree is built.
 *
 * Highlighting modes:
 *  - Step 2 (boundaries set, no active index): each situation's full
 *    wording in a distinct colour -- the text detector's own view,
 *    so nothing the split found is silently missing on the right.
 *  - Step 3 (active index set): leaves already captured for the
 *    active situation (+ prerequisites), coloured by situation.
 *  - Step 1 / no split: every leaf that anchors onto the text.
 */

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MenuBookRoundedIcon from "@mui/icons-material/MenuBookRounded";

import { collectTreeHighlights } from "./HighlightWizard/leafTextMatch";
import { pathwayTextWindow } from "./HighlightWizard/wizardMapping";
import {
  HIGHLIGHT_COLORS,
  type HighlightSpan,
} from "./SentenceEditor/HighlightableRecommendationText";
import {
  cleanPathwayText,
  type PathwayTextBoundary,
} from "./SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode } from "./types";

interface Props {
  recommendationText?: string | null;
  /** Current rule tree -- when present, its leaves' matching words are
   *  highlighted in the quote below. Omit (or pass null) to render the
   *  quote plain, e.g. before any tree exists yet. */
  tree?: EditableLogicNode | null;
  /**
   * All pathway text boundaries (Step 2's proposed / confirmed split).
   * Together with `activePathwayIndex`, picks the highlight mode:
   * boundaries + null index = Step 2 colour-per-situation overview;
   * boundaries + index = Step 3 scoped-to-active capture view.
   */
  pathwayBoundaries?: PathwayTextBoundary[] | null;
  /** Index into `pathwayBoundaries` for the situation currently being
   *  built in Step 3. Null/undefined on Step 2 means "show every
   *  situation in its own colour". */
  activePathwayIndex?: number | null;
}

/** Distinct, readable colours per situation letter (A, B, C, ...).
 *  Cycles if a recommendation has more situations than the palette.
 *  Teal / amber / green / rose / sky / orange -- deliberately not a
 *  purple-gradient cluster. */
const SITUATION_COLORS: Array<{ bgcolor: string; color: string }> = [
  { bgcolor: "#CCFBF1", color: "#115E59" }, // teal - A
  { bgcolor: "#FEF3C7", color: "#92400E" }, // amber - B
  { bgcolor: "#DCFCE7", color: "#14532D" }, // green - C
  { bgcolor: "#FFE4E6", color: "#9F1239" }, // rose - D
  { bgcolor: "#E0F2FE", color: "#075985" }, // sky - E
  { bgcolor: "#FFEDD5", color: "#9A3412" }, // orange - F
];

/** Colour for a situation index, or the shared confirmed green for a
 *  prerequisite (no pathway). Exported for direct unit testing. */
export function situationHighlightColor(
  pathwayIndex: number | null | undefined,
): { bgcolor: string; color: string } {
  if (pathwayIndex == null) return HIGHLIGHT_COLORS.confirmed;
  return SITUATION_COLORS[pathwayIndex % SITUATION_COLORS.length];
}

/**
 * One span per situation boundary, tagged with its pathway index so
 * the renderer can paint each a different colour. Strips a dangling
 * trailing ", or" connector (see `cleanPathwayText`) so the highlight
 * ends on the situation's own wording, not the next-pathway glue.
 */
export function buildSituationBoundaryHighlights(
  boundaries: PathwayTextBoundary[],
): HighlightSpan[] {
  // Tree-rehydrated situations (table-driven rules) have no quote spans
  // -- painting cleaned label length at start:0 stacked five colours on
  // the same prefix (e.g. "1.5.9 Arran"). Skip those, and any other
  // zero-width placeholder, so Step 2 does not invent fake highlights.
  return boundaries.flatMap((boundary, index) => {
    if (boundary.source === "tree" || boundary.end <= boundary.start) {
      return [];
    }
    const cleaned = cleanPathwayText(boundary.text);
    const local = cleaned ? boundary.text.indexOf(cleaned) : 0;
    const start = boundary.start + Math.max(0, local);
    const end =
      start +
      (cleaned ? cleaned.length : Math.max(0, boundary.end - boundary.start));
    if (end <= start) return [];
    return [
      {
        start,
        end,
        kind: "confirmed" as const,
        pathwayIndex: index,
      },
    ];
  });
}

/**
 * Restricts `highlights` to wording the reviewer can actually act on
 * right now: anything outside every pathway's extended text window (a
 * prerequisite) plus anything inside the ACTIVE window. Uses
 * `pathwayTextWindow` -- not raw `boundary.end` -- so nested-list
 * wording that sits past a structural lead `<li>` still belongs to
 * that situation instead of lighting up as a false prerequisite.
 * Step 2 (active index null) deliberately drops pathway-owned tree
 * highlights -- that step uses `buildSituationBoundaryHighlights`
 * instead so every word the detector found is visible.
 */
export function scopeHighlightsToActiveSituation(
  highlights: HighlightSpan[],
  pathwayBoundaries: PathwayTextBoundary[] | null | undefined,
  activePathwayIndex: number | null | undefined,
  textLength = 0,
): HighlightSpan[] {
  if (!pathwayBoundaries || pathwayBoundaries.length === 0) return highlights;
  const windows = pathwayBoundaries.map((_, i) => {
    const extended = pathwayTextWindow(pathwayBoundaries, i, textLength);
    const raw = pathwayBoundaries[i];
    return extended ?? { start: raw.start, end: raw.end };
  });
  const active =
    activePathwayIndex != null ? windows[activePathwayIndex] : undefined;
  const fallsWithin = (span: HighlightSpan, range: { start: number; end: number }) =>
    span.start < range.end && range.start < span.end;
  return highlights.filter((span) => {
    if (active && fallsWithin(span, active)) return true;
    const inOther = windows.some(
      (w, i) => i !== activePathwayIndex && fallsWithin(span, w),
    );
    return !inOther;
  });
}

export type MergedHighlightRange = {
  start: number;
  end: number;
  pathwayIndex?: number | null;
};

/** Merges overlapping/adjacent highlight spans of the SAME situation
 *  only -- never glues situation A into situation B, which would wipe
 *  the per-colour distinction. Exported for direct unit testing. */
export function mergeHighlightRanges(
  highlights: HighlightSpan[],
): MergedHighlightRange[] {
  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const merged: MergedHighlightRange[] = [];
  for (const span of sorted) {
    const last = merged[merged.length - 1];
    const samePathway = last && last.pathwayIndex === span.pathwayIndex;
    if (last && samePathway && span.start <= last.end) {
      last.end = Math.max(last.end, span.end);
    } else {
      merged.push({
        start: span.start,
        end: span.end,
        pathwayIndex: span.pathwayIndex,
      });
    }
  }
  return merged;
}

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
    const palette = situationHighlightColor(range.pathwayIndex);
    nodes.push(
      <Box
        key={`mark-${i}`}
        component="mark"
        data-situation-index={
          range.pathwayIndex == null ? "prereq" : String(range.pathwayIndex)
        }
        sx={{
          bgcolor: palette.bgcolor,
          color: palette.color,
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

function pickHighlights(
  recommendationText: string | null | undefined,
  tree: EditableLogicNode | null | undefined,
  pathwayBoundaries: PathwayTextBoundary[] | null | undefined,
  activePathwayIndex: number | null | undefined,
): { highlights: HighlightSpan[]; mode: "overview" | "scoped" | "all" } {
  const hasSplit = Boolean(pathwayBoundaries && pathwayBoundaries.length > 1);
  if (hasSplit && activePathwayIndex == null) {
    return {
      highlights: buildSituationBoundaryHighlights(pathwayBoundaries!),
      mode: "overview",
    };
  }
  const all = collectTreeHighlights(recommendationText, tree);
  if (hasSplit && activePathwayIndex != null) {
    const textLength = recommendationText?.length ?? 0;
    const activeWindow =
      pathwayTextWindow(pathwayBoundaries!, activePathwayIndex, textLength) ??
      pathwayBoundaries![activePathwayIndex];
    const scoped = scopeHighlightsToActiveSituation(
      all,
      pathwayBoundaries,
      activePathwayIndex,
      textLength,
    ).map((span) => {
      const inActive =
        span.start < activeWindow.end && activeWindow.start < span.end;
      // Active-situation captures paint in that situation's colour;
      // prerequisites (outside every pathway window) stay the shared green.
      return { ...span, pathwayIndex: inActive ? activePathwayIndex : null };
    });
    return { highlights: scoped, mode: "scoped" };
  }
  return { highlights: all, mode: "all" };
}

function legendFor(
  mode: "overview" | "scoped" | "all",
  hasHighlights: boolean,
): string {
  if (!hasHighlights) {
    return "Keep checking this against what you pick on the left. You'll see the full rule summary once you reach Review.";
  }
  if (mode === "overview") {
    return "Each colour is a different situation from the split on the left. Check the colours match the rows before you continue.";
  }
  if (mode === "scoped") {
    return "Highlighted words are already captured for this situation (and anything that applies to every situation). Check the rest against what's still missing.";
  }
  return "Highlighted words are already captured on the left. Check the rest against what's still missing.";
}

export default function GuidelineQuotePanel({
  recommendationText,
  tree,
  pathwayBoundaries,
  activePathwayIndex,
}: Props) {
  const { highlights, mode } = useMemo(
    () =>
      pickHighlights(
        recommendationText,
        tree,
        pathwayBoundaries,
        activePathwayIndex,
      ),
    [recommendationText, tree, pathwayBoundaries, activePathwayIndex],
  );

  return (
    <Box
      role="region"
      aria-label="NICE guideline wording for this rule"
      data-tour="er-02-quote"
      sx={{
        position: "sticky",
        top: 0,
        alignSelf: "flex-start",
        p: { xs: 1.5, md: 2 },
        display: "flex",
        flexDirection: "column",
        gap: 1.25,
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
            px: 2,
            py: 1.5,
            borderLeft: "4px solid",
            borderColor: "primary.main",
            bgcolor: "background.paper",
            borderRadius: "0 8px 8px 0",
          }}
        >
          <Typography
            variant="body2"
            sx={{ fontStyle: "italic", lineHeight: 1.55, color: "text.primary" }}
          >
            {renderHighlightedQuote(recommendationText, highlights)}
          </Typography>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          This rule has no guideline text to show.
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.45 }}>
        {legendFor(mode, highlights.length > 0)}
      </Typography>
    </Box>
  );
}
