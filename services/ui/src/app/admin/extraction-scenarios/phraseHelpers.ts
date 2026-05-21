/**
 * Shared helpers for extraction scenario phrase rows.
 */

import type { ExpectedPhrase } from "./types";

export const SEMANTIC_TAG_OPTIONS = [
  "finding",
  "disorder",
  "observable_entity",
  "procedure",
  "situation",
  "pharmaceutical",
  "body_structure",
  "social_context",
] as const;

export function phraseText(entry: string | ExpectedPhrase): string {
  if (typeof entry === "string") return entry;
  return entry.text ?? "";
}

export function phraseTag(entry: string | ExpectedPhrase): string {
  if (typeof entry === "string") return "finding";
  return entry.semantic_tag || "finding";
}

export function toExpectedPhrases(
  entries: Array<string | ExpectedPhrase> | undefined,
): ExpectedPhrase[] {
  return (entries ?? []).map((entry) => ({
    text: phraseText(entry),
    semantic_tag: phraseTag(entry),
  }));
}

export function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function listToLines(values: string[] | undefined): string {
  return (values ?? []).join("\n");
}

export function commaListToArray(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function arrayToCommaList(values: string[] | undefined): string {
  return (values ?? []).join(", ");
}
