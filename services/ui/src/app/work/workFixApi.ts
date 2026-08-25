/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59, DI-6BD7B681
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */

import {
  ensurePhrase,
  fetchPhraseItem,
  publishPhrase,
  savePhraseDraft,
  submitPhrase,
  type UncodedPhrase,
} from "@/app/settings/surface-forms/phraseMappingsApi";

export type WorkFixKind = "map" | "exclude" | "context" | "teach";
export type { UncodedPhrase };

const ADMIN_FIX_ERROR =
  "You need admin access to save this rule. Ask an admin, or finish this one task.";

export async function postWorkFix<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(body),
  });
  if (res.status === 403) throw new Error(ADMIN_FIX_ERROR);
  if (!res.ok) throw new Error("Could not save. Please try again.");
  if (res.status === 204) return {} as T;
  return (await res.json()) as T;
}

export async function loadWorkPhrase(input: {
  phrase: string;
  entityLabel?: string;
  encounterText?: string;
  extractedSource?: string;
}): Promise<UncodedPhrase> {
  return ensurePhrase({
    phrase_key: input.phrase,
    extracted_tag: input.entityLabel ?? "",
    extracted_source: input.extractedSource ?? "",
    sample_span: input.phrase,
    sample_sentence: input.encounterText ?? "",
  });
}

export async function refreshWorkPhrase(phrase: string): Promise<UncodedPhrase> {
  return fetchPhraseItem(phrase);
}

export async function savePhraseMapping(
  phrase: string,
  conceptId: string,
  conceptTerm = "",
): Promise<void> {
  await savePhraseDraft({
    phrase_key: phrase,
    action: "map",
    concept_id: conceptId,
    concept_term: conceptTerm,
  });
}

export async function saveSuppressRule(input: {
  entityText: string;
  entityLabel?: string;
  contextPhrase?: string;
  reviewId?: string | null;
}): Promise<void> {
  const reason = (input.contextPhrase || "Do not code this phrase").trim();
  await savePhraseDraft({
    phrase_key: input.entityText,
    action: "exclude",
    reason,
  });
}

export async function submitWorkPhrase(phrase: string): Promise<void> {
  await submitPhrase(phrase);
}

export async function deployWorkPhrase(phrase: string): Promise<void> {
  await publishPhrase(phrase);
}

export async function saveContextCue(input: {
  literal: string;
  category: string;
  direction: string;
}): Promise<void> {
  await postWorkFix("/api/training/context-rules", {
    literal: input.literal.trim(),
    category: input.category,
    direction: input.direction,
    max_scope: 5,
    description: "Added from My work engineer panel",
    example: "",
  });
}

export async function saveTeachExample(input: {
  span: string;
  letter: string;
  semantic_tag: string;
  assertion: string;
}): Promise<void> {
  await postWorkFix("/api/operations/extraction-reviews/few-shot", {
    span: input.span.trim(),
    letter: input.letter,
    semantic_tag: input.semantic_tag,
    assertion: input.assertion,
  });
}

export { savePhraseDraft, submitPhrase, publishPhrase };
