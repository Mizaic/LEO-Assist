/**
 * Build a facts/codes preview from Validation Lab stage JSON.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883
 */

import type { LabWorkItem, LabWorkPreview } from "../inspectorTypes";

const SBAR_KEYS = [
  "situation",
  "background",
  "assessment",
  "recommendation",
] as const;

const TEXT_KEYS = [
  "text",
  "surface",
  "mention",
  "term",
  "entity_text",
  "preferred_term",
  "lookup_term",
];
const CODE_KEYS = ["concept_id", "snomed_concept_id", "code", "conceptId"];
const SENTENCE_KEYS = ["evidence_sentence", "sentence", "sentence_text"];

export function workPreviewFromStage(
  output: Record<string, unknown> | null | undefined,
  input?: Record<string, unknown> | null,
  fallback?: LabWorkPreview | null,
): LabWorkPreview {
  const payload = output && typeof output === "object" ? output : {};
  const source = input && typeof input === "object" ? input : {};
  const sentences = pickSentences(payload, source);
  const fromOut = entityItems(payload, sentences);
  const items = fromOut.length ? fromOut : entityItems(source, sentences);
  const sbar = sbarItems(payload);
  const chosen = items.length ? items : sbar;
  const headline = headlineFor(payload, items, sbar) || fallback?.headline || "";
  if (!headline && !chosen.length) {
    return fallback || { headline: "", items: [] };
  }
  return { headline, items: chosen.slice(0, 8) };
}

function pickSentences(
  payload: Record<string, unknown>,
  source: Record<string, unknown>,
): unknown[] {
  const fromOut = sentenceList(payload);
  return fromOut.length ? fromOut : sentenceList(source);
}

function entityItems(
  payload: Record<string, unknown>,
  sentences: unknown[],
): LabWorkItem[] {
  const raw = payload.entities;
  if (!Array.isArray(raw)) return [];
  return itemsFromEntities(raw, sentences);
}

export function itemsFromEntities(
  raw: unknown[],
  sentences: unknown[] = [],
): LabWorkItem[] {
  const items: LabWorkItem[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const ev = entityEvidence(row as Record<string, unknown>, sentences);
    if (!ev.text) continue;
    const item: LabWorkItem = { kind: ev.code ? "code" : "fact", text: ev.text };
    if (ev.code) item.code = ev.code;
    if (ev.evidence) item.evidence = ev.evidence;
    if (ev.evidenceSentence) item.evidenceSentence = ev.evidenceSentence;
    items.push(item);
  }
  return items;
}

export function entityEvidence(
  ent: Record<string, unknown>,
  sentences: unknown[] = [],
): {
  text: string;
  code: string;
  evidence: string;
  evidenceSentence: string;
} {
  const text = firstStr(ent, TEXT_KEYS);
  return {
    text,
    code: entityCode(ent),
    evidence: firstStr(ent, ["evidence"]) || text,
    evidenceSentence:
      firstStr(ent, SENTENCE_KEYS) || sentenceForId(ent, sentences),
  };
}

export function formatEvidenceTooltip(item: {
  text: string;
  code?: string;
  evidence?: string;
  evidenceSentence?: string;
}): string {
  const lines = [item.code ? `${item.text} -- ${item.code}` : item.text];
  if (item.evidence) lines.push(`evidence: ${item.evidence}`);
  if (item.evidenceSentence) {
    lines.push(`evidence_sentence: ${item.evidenceSentence}`);
  }
  return lines.join("\n");
}

export function sentenceList(payload: Record<string, unknown>): unknown[] {
  return Array.isArray(payload.sentences) ? payload.sentences : [];
}

function sentenceForId(
  ent: Record<string, unknown>,
  sentences: unknown[],
): string {
  const sid = String(ent.__sentence_id || ent.sentence_id || "").trim();
  if (!sid) return "";
  for (const row of sentences) {
    if (!row || typeof row !== "object") continue;
    const rec = row as Record<string, unknown>;
    const id = String(rec.sentence_id || rec.id || "").trim();
    if (id === sid) return String(rec.text || "").trim();
  }
  return "";
}

export function isEntityList(value: unknown): boolean {
  if (!Array.isArray(value) || value.length === 0) return false;
  return value.some((row) => {
    if (!row || typeof row !== "object") return false;
    return Boolean(firstStr(row as Record<string, unknown>, TEXT_KEYS));
  });
}

function entityCode(ent: Record<string, unknown>): string {
  const direct = firstStr(ent, CODE_KEYS);
  if (direct) return direct;
  const coding = ent.coding;
  if (coding && typeof coding === "object") {
    return firstStr(coding as Record<string, unknown>, CODE_KEYS);
  }
  return "";
}

function sbarItems(payload: Record<string, unknown>): LabWorkItem[] {
  const report = payload.sbar_report;
  const sections =
    report && typeof report === "object"
      ? (report as Record<string, unknown>)
      : payload.sbar_sections && typeof payload.sbar_sections === "object"
        ? (payload.sbar_sections as Record<string, unknown>)
        : null;
  if (!sections) return [];
  const items: LabWorkItem[] = [];
  for (const key of SBAR_KEYS) {
    const text = String(sections[key] || "").trim();
    if (!text) continue;
    items.push({ kind: "sbar", text: `${key}: ${clip(text, 80)}` });
  }
  return items;
}

function headlineFor(
  payload: Record<string, unknown>,
  entities: LabWorkItem[],
  sbar: LabWorkItem[],
): string {
  if (entities.length) {
    const coded = entities.filter((item) => item.kind === "code").length;
    const noun = entities.length === 1 ? "fact" : "facts";
    if (coded) return `Coded ${coded} of ${entities.length} ${noun}`;
    return `Found ${entities.length} ${noun}`;
  }
  if (Array.isArray(payload.entities)) {
    return "Found 0 facts";
  }
  if (sbar.length) return `Drafted ${sbar.length} of 4 sections`;
  if (String(payload.sbar_status || "") === "error") {
    return "Draft assessment failed";
  }
  return "";
}

function firstStr(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = String(row[key] || "").trim();
    if (value) return value;
  }
  return "";
}

function clip(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 3)}...`;
}
