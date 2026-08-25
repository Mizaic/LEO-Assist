/**
 * Selected-fact letter mentions for extraction quality review.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
 */
import {
  letterHighlightMarks,
  type LetterMark,
} from "@/app/admin/validation-lab/letterHighlight";
import { escapeRegex } from "@/components/mission-control/HighlightedText";

import type { DraftEntity } from "./ExtractionReviewFacts";

export function mentionRegex(term: string): RegExp | null {
  const cleaned = term.trim();
  if (!cleaned) return null;
  const escaped = escapeRegex(cleaned);
  const pattern = /^\w+$/.test(cleaned) ? `\\b${escaped}\\b` : escaped;
  return new RegExp(pattern, "gi");
}

export function countMentions(letter: string, term: string): number {
  const pattern = mentionRegex(term);
  if (!pattern) return 0;
  return letter.match(pattern)?.length ?? 0;
}

export function mentionCopy(term: string, count: number): string {
  if (count <= 0) return `${term} was not found on the letter`;
  if (count === 1) return `${term} appears once on the letter`;
  return `${term} appears ${count} times on the letter`;
}

export function focusedReviewMarks(
  entities: DraftEntity[],
  focusText: string,
): LetterMark[] {
  const picked =
    entities.find((entity) => entity.text === focusText) ?? entities[0];
  if (!picked?.text) return [];
  return letterHighlightMarks([
    {
      text: picked.text,
      assertion: picked.assertion,
      semanticTag: picked.semantic_tag,
    },
  ]);
}
