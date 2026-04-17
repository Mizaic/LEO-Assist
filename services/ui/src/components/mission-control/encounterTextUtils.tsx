import React from "react";
import Box from "@mui/material/Box";

// Date / regex / sentence helpers shared by the Encounter text surface.
// See DI-LEO-AI-179 / DO-LEO-AI-178.

export const MILESTONE_LABELS: Record<string, string> = {
  first_presentation: "First seen",
  gp_referral: "Referred",
  specialist_visit: "Specialist",
  specialist_outcome_letter: "Outcome letter",
  cancer_diagnosis: "Diagnosed",
  benign_closure: "Closed",
};

export function inRange(
  date: string,
  from: string | null,
  to: string | null
): boolean {
  if (!date) return false;
  if (from && date < from) return false;
  if (to && date > to) return false;
  return true;
}

export function inMsRange(
  date: string | null | undefined,
  fromMs: number,
  toMs: number
): boolean {
  if (!date) return false;
  const t = Date.parse(date);
  if (!Number.isFinite(t)) return false;
  return t >= fromMs && t <= toMs;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return String(iso).slice(0, 10);
  }
}

export function escapeRegex(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Wrap each case-insensitive occurrence of `query` in a <mark> so the
// reader can quickly see why an encounter matched their search.
export function highlightSearchMatches(
  text: string,
  query: string
): React.ReactNode {
  const trimmed = query.trim();
  if (!trimmed || !text) return text;
  const pattern = new RegExp(`(${escapeRegex(trimmed)})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <Box
        component="mark"
        key={index}
        sx={{
          bgcolor: "#fde68a",
          color: "inherit",
          px: 0.25,
          borderRadius: "2px",
          fontWeight: 600,
        }}
      >
        {part}
      </Box>
    ) : (
      part
    )
  );
}

export function deriveEvidenceSentence(
  encounterText: string | null | undefined,
  mention: string | null | undefined
): string | null {
  const text = (encounterText ?? "").trim();
  const span = (mention ?? "").trim();
  if (!text || !span) return null;
  const lowerText = text.toLowerCase();
  const lowerSpan = span.toLowerCase();
  const idx = lowerText.indexOf(lowerSpan);
  if (idx < 0) return null;

  const leftBoundary = Math.max(
    text.lastIndexOf(".", idx),
    text.lastIndexOf("\n", idx)
  );
  const rightDot = text.indexOf(".", idx + span.length);
  const rightNl = text.indexOf("\n", idx + span.length);
  const rightCandidates = [rightDot, rightNl].filter((v) => v >= 0);
  const rightBoundary =
    rightCandidates.length > 0 ? Math.min(...rightCandidates) : text.length;
  const start = leftBoundary >= 0 ? leftBoundary + 1 : 0;
  const end = rightBoundary < text.length ? rightBoundary + 1 : text.length;
  const sentence = text.slice(start, end).trim();
  return sentence || null;
}

// Short text preview for the timeline scrubber hover card and dot
// aria-labels. Trims whitespace, collapses newlines, truncates to
// `maxChars` with an ellipsis.
export function shortPreview(
  text: string | null | undefined,
  maxChars = 120
): string {
  const cleaned = (text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "";
  if (cleaned.length <= maxChars) return cleaned;
  return cleaned.slice(0, maxChars - 1).trimEnd() + "...";
}
