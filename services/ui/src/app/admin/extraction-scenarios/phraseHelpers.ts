/**
 * Shared helpers for extraction scenario phrase rows.
 */

import type {
  ExpectedPhrase,
  ExtractionScenarioDetail,
  ObservableValue,
} from "./types";

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

export function isObservableEntityTag(tag: string): boolean {
  return tag.trim().toLowerCase() === "observable_entity";
}

export function normaliseObservableKey(value: string): string {
  return value.trim().toLowerCase();
}

export function buildObservableValueLookup(
  expectedObservables?: ExtractionScenarioDetail["expected_observables"],
  bloodResults?: ExtractionScenarioDetail["blood_results"],
): Map<string, ObservableValue> {
  const lookup = new Map<string, ObservableValue>();
  for (const obs of expectedObservables ?? []) {
    lookup.set(normaliseObservableKey(obs.text), {
      value: obs.value,
      unit: obs.unit,
    });
  }

  const blood = bloodResults;
  if (blood && !Array.isArray(blood) && Array.isArray(blood.results)) {
    for (const result of blood.results) {
      const info: ObservableValue = {
        value: result.value == null ? undefined : String(result.value),
        unit: result.unit,
      };
      lookup.set(normaliseObservableKey(result.test_name), info);
      if (result.display_name) {
        lookup.set(normaliseObservableKey(result.display_name), info);
      }
    }
  }
  return lookup;
}

export function toExpectedPhrases(
  entries: Array<string | ExpectedPhrase> | undefined,
  valueLookup?: Map<string, ObservableValue>,
): ExpectedPhrase[] {
  return (entries ?? []).map((entry) => {
    const text = phraseText(entry);
    const semantic_tag = phraseTag(entry);
    const phrase: ExpectedPhrase = { text, semantic_tag };
    if (typeof entry !== "string") {
      if (entry.concept_id) phrase.concept_id = entry.concept_id;
      if (entry.preferred_term) phrase.preferred_term = entry.preferred_term;
      if (entry.value || entry.unit) {
        phrase.value = entry.value ?? "";
        phrase.unit = entry.unit ?? "";
        return phrase;
      }
    }
    if (isObservableEntityTag(semantic_tag)) {
      const matched = valueLookup?.get(normaliseObservableKey(text));
      phrase.value = matched?.value ?? "";
      phrase.unit = matched?.unit ?? "";
    }
    return phrase;
  });
}

export function buildExpectedStringsFromPhrases(phrases: ExpectedPhrase[]): ExpectedPhrase[] {
  return phrases
    .map((row) => {
      const item: ExpectedPhrase = {
        text: row.text.trim(),
        semantic_tag: row.semantic_tag.trim() || "finding",
      };
      const conceptId = row.concept_id?.trim();
      const preferredTerm = row.preferred_term?.trim();
      if (conceptId) item.concept_id = conceptId;
      if (preferredTerm) item.preferred_term = preferredTerm;
      return item;
    })
    .filter((row) => row.text.length > 0);
}

export function buildExpectedObservablesFromPhrases(
  phrases: ExpectedPhrase[],
): NonNullable<ExtractionScenarioDetail["expected_observables"]> {
  return phrases
    .filter((row) => isObservableEntityTag(row.semantic_tag) && row.text.trim())
    .map((row) => {
      const item: NonNullable<ExtractionScenarioDetail["expected_observables"]>[number] = {
        text: row.text.trim(),
      };
      const value = row.value?.trim();
      const unit = row.unit?.trim();
      if (value) item.value = value;
      if (unit) item.unit = unit;
      return item;
    })
    .filter((row) => row.value || row.unit);
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
