/**
 * Pure helpers + shared types for the PortEdge probe surface
 * (Phase 6b-vi decomposition).
 *
 * Extracted verbatim from the legacy PortEdge.tsx (1781 LOC) into a
 * focused, side-effect-free module. No React imports here — keeps
 * helpers cheap to reason about and unit-test.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

export type PathSegment = string | number;
export type SearchMatch = { path: PathSegment[]; preview: string };
export type ProbeTab = "changes" | "data" | "validate";
export type StateChangeKind = "added" | "removed" | "changed";

export type PostProcessingLayerTrace = {
  layer_id: string;
  name: string;
  status: string;
  before_count: number;
  after_count: number;
  added_count: number;
  removed_count: number;
  updated_count: number;
  duration_ms: number;
  error?: string;
};

export type StateChange = {
  kind: StateChangeKind;
  path: PathSegment[];
  beforeValue: unknown;
  afterValue: unknown;
};

export const PRIORITY_KEYS = [
  "verification_result",
  "guidance_rules",
  "rules",
  "matches",
  "codes",
  "entities",
  "sentences",
  "errors",
  "is_verified",
  "status",
];
export const MAX_DIFF_DEPTH = 4;
export const MAX_DIFF_ENTRIES = 24;
export const MAX_DIFF_CHILDREN = 18;

export function probeKey(s: string, t: string): string {
  return `${s}|${t}`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asPostProcessingTrace(value: unknown): PostProcessingLayerTrace[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is PostProcessingLayerTrace => {
    if (!isRecord(item)) return false;
    return typeof item.name === "string"
      && typeof item.status === "string"
      && typeof item.before_count === "number"
      && typeof item.after_count === "number";
  });
}

export function safeStringify(value: unknown, spacing = 2): string {
  try {
    return JSON.stringify(value, null, spacing) ?? "null";
  } catch {
    return "[unserializable]";
  }
}

export function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return truncate(value.replace(/\s+/g, " "), 120);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return truncate(safeStringify(value, 0), 120);
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function friendlyError(raw: string): string {
  if (/invalid JSON/i.test(raw) || /JSONDecodeError/i.test(raw) || /json\.loads/i.test(raw))
    return "The AI replied with plain text instead of the expected format. The step carried on without it.";
  if (/timeout/i.test(raw))
    return "This step took too long and was stopped.";
  if (/connection|ECONNREFUSED|network/i.test(raw))
    return "Could not reach the service — it may be offline.";
  if (/ImportError|ModuleNotFound/i.test(raw))
    return "A required library is missing on the server.";
  if (raw.length > 120) return `${raw.slice(0, 100)}…`;
  return raw;
}

export function summarizeValue(value: unknown): string {
  if (value === null || value === undefined) return "empty";
  if (typeof value === "string") return value.length > 140 ? `${value.length} chars` : truncate(value.replace(/\s+/g, " "), 90);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isRecord(value)) return `${Object.keys(value).length} field${Object.keys(value).length === 1 ? "" : "s"}`;
  return truncate(String(value), 90);
}

const PREVIEW_KEYS = [
  "text", "display", "name", "mention", "type", "label", "assertion",
  "code", "title", "semantic_tag", "lookup_term",
];

/** Produce a short, human-readable preview for entity-like objects in diffs. */
export function previewForChange(value: unknown, _path: PathSegment[], maxParts = 2): string {
  if (value === null || value === undefined) return value === undefined ? "—" : "null";
  if (typeof value === "string") return truncate(value.replace(/\s+/g, " "), 60);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isRecord(value)) {
    const parts: string[] = [];
    for (const k of PREVIEW_KEYS) {
      if (k in value && value[k] != null) {
        const v = value[k];
        parts.push(typeof v === "string" ? truncate(v, 50) : String(v));
        if (parts.length >= maxParts) break;
      }
    }
    if (parts.length > 0) return parts.join(" · ");
    return `${Object.keys(value).length} field${Object.keys(value).length === 1 ? "" : "s"}`;
  }
  return truncate(String(value), 60);
}

/** Richer preview for added items — show more fields. */
export function previewForAdded(value: unknown, path: PathSegment[]): string {
  return previewForChange(value, path, 4);
}

export function valueTone(value: unknown): string {
  if (Array.isArray(value)) return "#fab387";
  if (typeof value === "boolean") return "#cba6f7";
  if (typeof value === "number") return "#a6e3a1";
  if (isRecord(value)) return "#89dceb";
  return "#cdd6f4";
}

export function pathToString(path: PathSegment[]): string {
  return path.reduce<string>((acc, part, index) => {
    if (typeof part === "number") return `${acc}[${part}]`;
    if (index === 0) return String(part);
    return `${acc}.${String(part)}`;
  }, "");
}

export function describePath(path: PathSegment[]): string {
  return pathToString(path) || "pipeline_state";
}

export function isTerminologyRow(value: unknown): boolean {
  return isRecord(value) && ("code" in value || "display" in value || "system" in value);
}

export function isGuidanceRuleRow(value: unknown): boolean {
  return isRecord(value) && (
    "condition" in value
    || "action" in value
    || "recommendation" in value
    || "rule" in value
    || "title" in value
  );
}

export function getObjectColumns(rows: Record<string, unknown>[]): string[] {
  const priority = ["code", "display", "system", "title", "name", "condition", "action", "recommendation", "status", "confidence"];
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return keys
    .sort((a, b) => {
      const ai = priority.indexOf(a);
      const bi = priority.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    })
    .slice(0, 5);
}
