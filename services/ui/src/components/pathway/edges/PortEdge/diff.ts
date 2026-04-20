/**
 * Diff + search + tree-state helpers for the PortEdge probe surface
 * (Phase 6b-vi decomposition).
 *
 * These helpers walk the pipeline-state object graph to produce
 * change lists, search matches and default expansion sets used by
 * the inspector drawer and probe monitor.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
import {
  MAX_DIFF_CHILDREN,
  MAX_DIFF_DEPTH,
  MAX_DIFF_ENTRIES,
  PRIORITY_KEYS,
  type PathSegment,
  type SearchMatch,
  type StateChange,
  type StateChangeKind,
  formatPrimitive,
  isRecord,
  pathToString,
  safeStringify,
} from "./utils";

export function getValueAtPath(root: unknown, path: PathSegment[]): unknown {
  let current: unknown = root;
  for (const part of path) {
    if (typeof part === "number") {
      if (!Array.isArray(current)) return undefined;
      current = current[part];
      continue;
    }
    if (!isRecord(current)) return undefined;
    current = current[part];
  }
  return current;
}

export function valuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (typeof left !== typeof right) return false;
  if ((Array.isArray(left) && Array.isArray(right)) || (isRecord(left) && isRecord(right))) {
    return safeStringify(left, 0) === safeStringify(right, 0);
  }
  return false;
}

export function collectStateChanges(
  beforeValue: unknown,
  afterValue: unknown,
  path: PathSegment[] = [],
  depth = 0,
  changes: StateChange[] = [],
): StateChange[] {
  if (changes.length >= MAX_DIFF_ENTRIES || valuesEqual(beforeValue, afterValue)) return changes;

  if (depth >= MAX_DIFF_DEPTH) {
    changes.push({ kind: "changed", path, beforeValue, afterValue });
    return changes;
  }

  if (Array.isArray(beforeValue) && Array.isArray(afterValue)) {
    const limit = Math.min(Math.max(beforeValue.length, afterValue.length), MAX_DIFF_CHILDREN);
    for (let index = 0; index < limit && changes.length < MAX_DIFF_ENTRIES; index += 1) {
      if (index >= beforeValue.length) {
        changes.push({ kind: "added", path: [...path, index], beforeValue: undefined, afterValue: afterValue[index] });
        continue;
      }
      if (index >= afterValue.length) {
        changes.push({ kind: "removed", path: [...path, index], beforeValue: beforeValue[index], afterValue: undefined });
        continue;
      }
      collectStateChanges(beforeValue[index], afterValue[index], [...path, index], depth + 1, changes);
    }
    if (changes.length === 0) {
      changes.push({ kind: "changed", path, beforeValue, afterValue });
    }
    return changes;
  }

  if (isRecord(beforeValue) && isRecord(afterValue)) {
    const keys = Array.from(new Set([...Object.keys(beforeValue), ...Object.keys(afterValue)])).sort();
    for (const key of keys.slice(0, MAX_DIFF_CHILDREN)) {
      if (changes.length >= MAX_DIFF_ENTRIES) break;
      if (!(key in beforeValue)) {
        changes.push({ kind: "added", path: [...path, key], beforeValue: undefined, afterValue: afterValue[key] });
        continue;
      }
      if (!(key in afterValue)) {
        changes.push({ kind: "removed", path: [...path, key], beforeValue: beforeValue[key], afterValue: undefined });
        continue;
      }
      collectStateChanges(beforeValue[key], afterValue[key], [...path, key], depth + 1, changes);
    }
    if (changes.length === 0) {
      changes.push({ kind: "changed", path, beforeValue, afterValue });
    }
    return changes;
  }

  if (beforeValue === undefined) {
    changes.push({ kind: "added", path, beforeValue, afterValue });
    return changes;
  }
  if (afterValue === undefined) {
    changes.push({ kind: "removed", path, beforeValue, afterValue });
    return changes;
  }

  changes.push({ kind: "changed", path, beforeValue, afterValue });
  return changes;
}

export function resolveInspectablePath(root: unknown, path: PathSegment[]): PathSegment[] {
  for (let index = path.length; index > 0; index -= 1) {
    const candidate = path.slice(0, index);
    if (getValueAtPath(root, candidate) !== undefined) return candidate;
  }
  return [];
}

export function toneForChange(kind: StateChangeKind): string {
  if (kind === "added") return "#a6e3a1";
  if (kind === "removed") return "#f38ba8";
  return "#89b4fa";
}

export function labelForChange(kind: StateChangeKind): string {
  if (kind === "added") return "Added";
  if (kind === "removed") return "Removed";
  return "Updated";
}

export function collectSearchMatches(
  value: unknown,
  query: string,
  path: PathSegment[] = [],
  matches: SearchMatch[] = [],
): SearchMatch[] {
  if (matches.length >= 40) return matches;
  const normalized = query.trim().toLowerCase();
  if (!normalized) return matches;

  const label = pathToString(path).toLowerCase();
  const preview = formatPrimitive(value).toLowerCase();
  if (path.length > 0 && (label.includes(normalized) || preview.includes(normalized))) {
    matches.push({ path, preview: formatPrimitive(value) });
  }

  if (Array.isArray(value)) {
    value.slice(0, 50).forEach((item, index) => collectSearchMatches(item, query, [...path, index], matches));
    return matches;
  }

  if (isRecord(value)) {
    Object.entries(value).slice(0, 100).forEach(([key, child]) => {
      if (matches.length >= 40) return;
      collectSearchMatches(child, query, [...path, key], matches);
    });
  }

  return matches;
}

export function topLevelEntries(state: Record<string, unknown> | null): Array<[string, unknown]> {
  if (!state) return [];
  return Object.entries(state)
    .filter(([, value]) => value !== null && value !== undefined)
    .sort(([a], [b]) => {
      const ai = PRIORITY_KEYS.indexOf(a);
      const bi = PRIORITY_KEYS.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    });
}

export function getMeaningfulHighlights(entries: Array<[string, unknown]>): Array<[string, unknown]> {
  const scored = entries.map(([key, value]) => {
    const preferred = PRIORITY_KEYS.includes(key) ? 100 : 0;
    const primitive = typeof value === "boolean" || typeof value === "number" ? 40 : 0;
    const shortString = typeof value === "string" && value.length <= 80 ? 30 : 0;
    const complex = Array.isArray(value) || isRecord(value) ? 20 : 0;
    return { key, value, score: preferred + primitive + shortString + complex };
  });

  return scored
    .sort((a, b) => b.score - a.score || a.key.localeCompare(b.key))
    .slice(0, 4)
    .map(({ key, value }) => [key, value]);
}

export function getDefaultExpandedPaths(rootLabel: string, value: unknown): Set<string> {
  const expanded = new Set<string>([rootLabel]);
  if (Array.isArray(value)) {
    value.slice(0, 3).forEach((_, index) => expanded.add(pathToString([rootLabel, index])));
  } else if (isRecord(value)) {
    Object.keys(value).slice(0, 4).forEach((key) => expanded.add(pathToString([rootLabel, key])));
  }
  return expanded;
}

export function expandAncestors(path: PathSegment[]): Set<string> {
  const expanded = new Set<string>();
  for (let i = 1; i <= path.length; i += 1) expanded.add(pathToString(path.slice(0, i)));
  return expanded;
}
