/**
 * Collect letter marks for the selected pipeline stage.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 */

import type { LabWorkItem, LabWorkPreview } from "./inspectorTypes";
import {
  itemsFromEntities,
  plainLetterText,
  sentenceList,
  workPreviewFromStage,
} from "./inspector/stageWorkItems";
import { assertionKey } from "./letterMarkStyle";
import { isCodingStep, isFirstFactStep } from "./reviewWalk";

export const LETTER_HIGHLIGHT_MIN = 3;

export type LetterChange =
  | "stable"
  | "new"
  | "context"
  | "kind"
  | "coded"
  | "uncoded"
  | "dropped";

export interface LetterMark {
  term: string;
  assertion: string;
  semanticTag: string;
  code?: string;
  change?: LetterChange;
}

export function letterHighlightTerms(
  items: Array<{ text?: string; evidence?: string }>,
  focus?: string,
): string[] {
  return letterHighlightMarks(items, focus).map((mark) => mark.term);
}

export function letterHighlightMarks(
  items: Array<{
    text?: string;
    evidence?: string;
    assertion?: string;
    semanticTag?: string;
    code?: string;
  }>,
  focus?: string,
): LetterMark[] {
  const byKey = new Map<string, LetterMark>();
  pushMark(byKey, focus, "", "", "");
  for (const item of items) {
    pushMark(
      byKey,
      item.evidence || item.text,
      item.assertion || "",
      item.semanticTag || "",
      item.code || "",
    );
    if (item.evidence && item.text && item.evidence !== item.text) {
      pushMark(
        byKey,
        item.text,
        item.assertion || "",
        item.semanticTag || "",
        item.code || "",
      );
    }
  }
  return Array.from(byKey.values()).sort((a, b) => b.term.length - a.term.length);
}

function pushMark(
  byKey: Map<string, LetterMark>,
  raw: string | undefined,
  assertion: string,
  semanticTag: string,
  code: string,
): void {
  const term = plainLetterText(raw || "");
  if (term.length < LETTER_HIGHLIGHT_MIN) return;
  const key = term.toLowerCase();
  const next: LetterMark = { term, assertion, semanticTag };
  if (code) next.code = code;
  const existing = byKey.get(key);
  byKey.set(key, existing ? mergeMark(existing, next) : next);
}

function mergeMark(existing: LetterMark, next: LetterMark): LetterMark {
  return {
    term: existing.term,
    assertion: existing.assertion || next.assertion,
    semanticTag: existing.semanticTag || next.semanticTag,
    code: existing.code || next.code,
  };
}

export function stageLetterHighlights(
  selectedStepId: string,
  spans: Array<{ step_id: string; work_preview?: LabWorkPreview }>,
  stageDetail: {
    step_id?: string;
    output?: Record<string, unknown> | null;
    input?: Record<string, unknown> | null;
  } | null,
  focus?: string,
): LetterMark[] {
  const selected = spans.find((row) => row.step_id === selectedStepId);
  const ready = stageDetail?.step_id === selectedStepId;
  const preview = workPreviewFromStage(
    ready ? stageDetail?.output : null,
    ready ? stageDetail?.input : null,
    selected?.work_preview,
  );
  const current = letterHighlightMarks(preview.items || [], focus);
  if (!ready || isFirstFactStep(selectedStepId)) return current;
  const previous = marksFromPayload(stageDetail?.input || {});
  return diffLetterMarks(previous, current, isCodingStep(selectedStepId));
}

export function marksFromPayload(payload: Record<string, unknown>): LetterMark[] {
  const raw = payload.entities;
  if (!Array.isArray(raw)) return [];
  return letterHighlightMarks(itemsFromEntities(raw, sentenceList(payload)));
}

export function diffLetterMarks(
  previous: LetterMark[],
  current: LetterMark[],
  coding: boolean,
): LetterMark[] {
  const prevBy = new Map(
    previous.map((mark) => [mark.term.toLowerCase(), mark]),
  );
  const seen = new Set<string>();
  const out: LetterMark[] = [];
  for (const curr of current) {
    const key = curr.term.toLowerCase();
    seen.add(key);
    out.push({ ...curr, change: classifyChange(prevBy.get(key), curr, coding) });
  }
  for (const prev of previous) {
    const key = prev.term.toLowerCase();
    if (seen.has(key)) continue;
    out.push({ ...prev, change: "dropped" });
  }
  return out.sort((a, b) => b.term.length - a.term.length);
}

function classifyChange(
  previous: LetterMark | undefined,
  current: LetterMark,
  coding: boolean,
): LetterChange {
  if (!previous) return "new";
  if (assertionKey(previous.assertion) !== assertionKey(current.assertion)) {
    return "context";
  }
  if (coding && !current.code) return "uncoded";
  if (current.code && !previous.code) return "coded";
  if ((previous.semanticTag || "") !== (current.semanticTag || "")) {
    return "kind";
  }
  return "stable";
}

/**
 * Diff two sets of work items (chips).
 * Mirrors diffLetterMarks but keyed on item.text instead of mark.term.
 */
export function diffWorkItems(
  previous: LabWorkItem[],
  current: LabWorkItem[],
  coding = false,
): LabWorkItem[] {
  const prevBy = new Map(previous.map((item) => [item.text.toLowerCase(), item]));
  const seen = new Set<string>();
  const out: LabWorkItem[] = [];
  for (const curr of current) {
    const key = curr.text.toLowerCase();
    seen.add(key);
    out.push({ ...curr, change: classifyWorkChange(prevBy.get(key), curr, coding) });
  }
  for (const prev of previous) {
    if (!seen.has(prev.text.toLowerCase())) {
      out.push({ ...prev, change: "dropped" });
    }
  }
  return out;
}

function classifyWorkChange(
  previous: LabWorkItem | undefined,
  current: LabWorkItem,
  coding: boolean,
): string {
  if (!previous) return "new";
  if (assertionKey(previous.assertion) !== assertionKey(current.assertion)) return "context";
  if (measurementChanged(previous, current)) return "measured";
  if (coding && !current.code) return "uncoded";
  if (current.code && !previous.code) return "coded";
  if ((previous.semanticTag || "") !== (current.semanticTag || "")) return "kind";
  return "stable";
}

function measurementChanged(prev: LabWorkItem, curr: LabWorkItem): boolean {
  const prevM = [prev.value, prev.unit].filter(Boolean).join(" ");
  const currM = [curr.value, curr.unit].filter(Boolean).join(" ");
  return Boolean(currM) && currM !== prevM;
}

export function changeLabel(change: LetterChange): string {
  if (change === "context") return "Context changed";
  if (change === "uncoded") return "Not coded";
  if (change === "dropped") return "Dropped";
  if (change === "new") return "New this step";
  if (change === "coded") return "Code added";
  if (change === "kind") return "Kind changed";
  return "";
}
