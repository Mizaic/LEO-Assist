/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import Box from "@mui/material/Box";
import { color, typography } from "@leo/design-system/tokens";

import LetterMarkdownView from "@/app/admin/validation-lab/LetterMarkdownView";
import type { LetterMark } from "@/app/admin/validation-lab/letterHighlight";

import type { UncodedPhrase } from "./phraseMappingsApi";

function sampleMarks(phrase: UncodedPhrase): LetterMark[] {
  const term = (phrase.sample_span || phrase.normalized || "").trim();
  if (!term) return [];
  return [
    {
      term,
      assertion: "present",
      semanticTag: phrase.extracted_tag || "",
      change: "uncoded",
    },
  ];
}

export function PhraseDetailHeader({ phrase }: { phrase: UncodedPhrase }) {
  const scorePct =
    phrase.last_score != null ? Math.round(Number(phrase.last_score) * 100) : null;
  const tagMismatch =
    phrase.extracted_tag &&
    phrase.last_best_tag &&
    phrase.extracted_tag.toLowerCase() !== phrase.last_best_tag.toLowerCase();
  const highlight = phrase.sample_span || phrase.normalized;
  return (
    <>
      <p
        style={{
          margin: 0,
          fontSize: 12,
          fontWeight: 600,
          color: color.text.caption,
          textTransform: "uppercase",
          letterSpacing: typography.letterSpacing.caption,
        }}
      >
        Pipeline rejected
      </p>
      <h2
        style={{
          margin: "4px 0 0",
          fontFamily: typography.fontFamily.heading,
          fontSize: 24,
          lineHeight: 1.05,
          letterSpacing: typography.letterSpacing.display,
          fontWeight: 700,
          color: color.text.primary,
          overflowWrap: "anywhere",
        }}
      >
        {phrase.normalized}
      </h2>
      {phrase.sample_sentence ? (
        <Box
          data-testid="phrase-sample-context"
          sx={{
            mt: 1.75,
            mb: 1.75,
            p: "12px 14px",
            borderRadius: "10px",
            bgcolor: color.surface.alt,
            color: color.text.secondary,
            fontSize: 14,
            maxHeight: 420,
            overflow: "auto",
          }}
        >
          <LetterMarkdownView
            text={phrase.sample_sentence}
            marks={sampleMarks(phrase)}
            focusTerm={highlight}
            emptyLabel=""
            testId="phrase-sample-highlight"
          />
        </Box>
      ) : null}
      <PhraseFacts
        phrase={phrase}
        scorePct={scorePct}
        tagMismatch={Boolean(tagMismatch)}
      />
    </>
  );
}

function PhraseFacts({
  phrase,
  scorePct,
  tagMismatch,
}: {
  phrase: UncodedPhrase;
  scorePct: number | null;
  tagMismatch: boolean;
}) {
  const chips = [
    phrase.extracted_tag ? "Extraction tag: " + phrase.extracted_tag : "",
    scorePct != null ? "Best score: " + scorePct + "%" : "",
    phrase.last_best_term
      ? "Best match: " +
        phrase.last_best_term +
        (phrase.last_best_tag ? " (" + phrase.last_best_tag + ")" : "")
      : "",
  ].filter(Boolean);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
      {chips.map((label) => (
        <span
          key={label}
          style={{
            background:
              tagMismatch && label.startsWith("Extraction")
                ? "rgba(180, 83, 9, 0.12)"
                : color.surface.alt,
            color:
              tagMismatch && label.startsWith("Extraction")
                ? color.status.warning
                : color.text.secondary,
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 12,
          }}
        >
          {label}
        </span>
      ))}
    </div>
  );
}
