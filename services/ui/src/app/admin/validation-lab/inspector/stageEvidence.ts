/**
 * Per-stage evidence for the Validation Lab review pane.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */

import { assertionLabel } from "../letterMarkStyle";
import type { LabWorkItem } from "../inspectorTypes";
import {
  extractRelationItems,
  workPreviewFromStage,
} from "./stageWorkItems";

export type StageStoryKind =
  | "facts"
  | "label_changes"
  | "links"
  | "check"
  | "codes"
  | "body_sites"
  | "persist"
  | "referral_reason"
  | "guidelines"
  | "gaps"
  | "sbar";

export type StageStory = {
  kind: StageStoryKind;
  lines: string[];
  items?: LabWorkItem[];
  empty?: string;
  headline?: string;
};

const KIND_MATCHERS: Array<[string, StageStoryKind]> = [
  ["snomed-relation-judge", "links"],
  ["relation-judge", "links"],
  ["relation-link", "links"],
  ["extraction-check", "check"],
  ["snomed-enrich", "body_sites"],
  ["coding-verify", "codes"],
  ["post-process", "label_changes"],
  ["post_process", "label_changes"],
  ["terminology", "codes"],
  ["referral-reason", "referral_reason"],
  ["compliance", "guidelines"],
  ["completeness", "gaps"],
  ["quality", "gaps"],
  ["persist", "persist"],
  ["sbar", "sbar"],
  ["coding", "codes"],
  ["extract", "facts"],
];

const SBAR_KEYS = [
  "situation",
  "background",
  "assessment",
  "recommendation",
] as const;

type Payload = Record<string, unknown>;

export function stageStory(
  stepId: string,
  output?: Payload | null,
  input?: Payload | null,
): StageStory {
  const payload = asRecord(output);
  const source = asRecord(input);
  const kind = kindFromStepId(stepId);
  return BUILDERS[kind](kind, payload, source);
}

export function kindFromStepId(stepId: string): StageStoryKind {
  const lower = stepId.toLowerCase();
  for (const [token, kind] of KIND_MATCHERS) {
    if (lower.includes(token)) return kind;
  }
  return "facts";
}

const BUILDERS: Record<
  StageStoryKind,
  (kind: StageStoryKind, output: Payload, input: Payload) => StageStory
> = {
  facts: factsStory,
  label_changes: labelChangeStory,
  links: linksStory,
  check: checkStory,
  codes: codesStory,
  body_sites: bodySiteStory,
  persist: persistStory,
  referral_reason: referralStory,
  guidelines: guidelineStory,
  gaps: gapsStory,
  sbar: sbarStory,
};

function factsStory(kind: StageStoryKind, output: Payload, input: Payload): StageStory {
  const preview = workPreviewFromStage(output, input);
  return { kind, lines: [], items: preview.items || [], headline: preview.headline };
}

function labelChangeStory(
  kind: StageStoryKind,
  output: Payload,
  input: Payload,
): StageStory {
  const before = entityMap(input);
  const after = entityMap(output);
  const lines: string[] = [];
  const items: LabWorkItem[] = [];
  for (const [key, was] of before) {
    const now = after.get(key);
    if (!now) {
      items.push({ kind: "fact", text: was.text, change: "dropped" });
      continue;
    }
    if (was.assertion && now.assertion && was.assertion !== now.assertion) {
      lines.push(
        `${was.text}: was ${assertionLabel(was.assertion)}, now treated as ${assertionLabel(now.assertion)}`,
      );
    }
  }
  for (const [key, now] of after) {
    if (before.has(key)) continue;
    items.push({ kind: "fact", text: now.text, change: "new" });
  }
  return emptyOr(kind, lines, items, "LEO did not change any labels.");
}

function linksStory(kind: StageStoryKind, output: Payload): StageStory {
  const items = extractRelationItems(entityList(output));
  if (!items.length) {
    return { kind, lines: [], empty: "LEO did not join any facts." };
  }
  const noun = items.length === 1 ? "link" : "links";
  return { kind, lines: [], items, headline: `Found ${items.length} ${noun}` };
}

function checkStory(kind: StageStoryKind, output: Payload, input: Payload): StageStory {
  const raw = output.llm_check_changes;
  if (Array.isArray(raw)) {
    const fromLog = changeLogLines(raw);
    if (fromLog.length) return { kind, lines: fromLog };
    return { kind, lines: [], empty: "LEO did not change anything." };
  }
  const nested = labelChangeStory("label_changes", output, input);
  if (nested.lines.length || nested.items?.length) {
    return { kind, lines: nested.lines, items: nested.items };
  }
  return { kind, lines: [], empty: "LEO did not change anything." };
}

function codesStory(kind: StageStoryKind, output: Payload, input: Payload): StageStory {
  return factsStory(kind, output, input);
}

function bodySiteStory(kind: StageStoryKind, output: Payload, input: Payload): StageStory {
  const preview = workPreviewFromStage(output, input);
  const items = (preview.items || []).filter((item) => item.kind === "inferred");
  if (!items.length) {
    return {
      kind,
      lines: [],
      empty: "LEO did not add body sites from the code book.",
    };
  }
  return { kind, lines: [], items, headline: preview.headline };
}

function persistStory(kind: StageStoryKind, output: Payload): StageStory {
  const n = persistCount(output);
  return { kind, lines: [], headline: `Saved ${n} coded facts` };
}

function referralStory(kind: StageStoryKind, output: Payload): StageStory {
  const reason = String(output.referral_reason || "").trim();
  if (reason) return { kind, lines: [reason] };
  return { kind, lines: [], empty: "LEO could not find a referral reason." };
}

function guidelineStory(kind: StageStoryKind, output: Payload): StageStory {
  const lines = matchedRuleNames(output);
  if (!lines.length) return { kind, lines: [], empty: "No care rule fired." };
  return { kind, lines };
}

function gapsStory(kind: StageStoryKind, output: Payload): StageStory {
  const lines = gapLines(output);
  if (!lines.length) return { kind, lines: [], empty: "LEO found no gaps." };
  return { kind, lines };
}

function sbarStory(kind: StageStoryKind, output: Payload): StageStory {
  const sections = sbarSections(output);
  const lines: string[] = [];
  for (const key of SBAR_KEYS) {
    const text = String(sections[key] || "").trim();
    if (!text) continue;
    lines.push(`${cap(key)}: ${text}`);
  }
  if (!lines.length) {
    return { kind, lines: [], empty: "LEO did not draft a summary." };
  }
  return { kind, lines };
}

function persistCount(output: Payload): number {
  const raw = Number(output.documents_written);
  if (Number.isFinite(raw) && raw >= 0) return raw;
  const preview = workPreviewFromStage(output);
  return (preview.items || []).filter((item) => item.code).length;
}

function matchedRuleNames(output: Payload): string[] {
  const bags = [
    output.matched_rules,
    record(output.compliance_result).matched_rules,
    record(output.guideline_diagnostics).matched,
  ];
  const names: string[] = [];
  for (const bag of bags) {
    if (!Array.isArray(bag)) continue;
    for (const row of bag) names.push(...ruleName(row));
  }
  return unique(names);
}

function ruleName(row: unknown): string[] {
  if (typeof row === "string" && row.trim()) return [row.trim()];
  const rec = record(row);
  const name = String(
    rec.name || rec.rule_name || rec.title || rec.rule_id || rec.id || "",
  ).trim();
  return name ? [name] : [];
}

function gapLines(output: Payload): string[] {
  const lines: string[] = [];
  const issues = [
    ...(Array.isArray(output.quality_issues) ? output.quality_issues : []),
    ...(Array.isArray(record(output.quality_report).issues)
      ? (record(output.quality_report).issues as unknown[])
      : []),
  ];
  for (const row of issues) {
    const rec = record(row);
    const text = String(rec.description || rec.message || rec.issue_type || "").trim();
    if (text) lines.push(text);
  }
  const missing = record(output.completeness_result).missing_groups;
  if (Array.isArray(missing)) {
    for (const row of missing) {
      const rec = record(row);
      const name = String(rec.name || rec.group || rec.title || "").trim();
      if (name) lines.push(name);
    }
  }
  return unique(lines);
}

function changeLogLines(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const lines: string[] = [];
  for (const row of raw) {
    const rec = record(row);
    const text = String(rec.text || "").trim();
    const type = String(rec.type || "").toLowerCase();
    if (!text) continue;
    if (type === "added") lines.push(`Added: ${text}`);
    else if (type.includes("drop")) lines.push(`Dropped: ${text}`);
    else lines.push(`${text}: ${type || "changed"}`);
  }
  return lines;
}

function sbarSections(output: Payload): Payload {
  const report = record(output.sbar_report);
  if (Object.keys(report).length) return report;
  return record(output.sbar_sections);
}

function entityMap(payload: Payload): Map<string, { text: string; assertion: string }> {
  const map = new Map<string, { text: string; assertion: string }>();
  for (const row of entityList(payload)) {
    const rec = record(row);
    const text = String(rec.text || rec.surface || rec.mention || rec.term || "").trim();
    if (!text) continue;
    map.set(text.toLowerCase(), {
      text,
      assertion: String(rec.assertion || "").trim(),
    });
  }
  return map;
}

function entityList(payload: Payload): unknown[] {
  return Array.isArray(payload.entities) ? payload.entities : [];
}

function emptyOr(
  kind: StageStoryKind,
  lines: string[],
  items: LabWorkItem[],
  empty: string,
): StageStory {
  if (!lines.length && !items.length) return { kind, lines: [], empty };
  return { kind, lines, items };
}

function asRecord(value: Payload | null | undefined): Payload {
  return value && typeof value === "object" ? value : {};
}

function record(value: unknown): Payload {
  return value && typeof value === "object" ? (value as Payload) : {};
}

function unique(items: string[]): string[] {
  return [...new Set(items)];
}

function cap(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}
