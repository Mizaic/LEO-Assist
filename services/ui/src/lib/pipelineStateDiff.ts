/**
 * Shared pipeline state diff helpers for Pathway probes and Lab inspector.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
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
} from "@/components/pathway/edges/PortEdge/utils";

export type { PathSegment, SearchMatch, StateChange, StateChangeKind };

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
  if (
    (Array.isArray(left) && Array.isArray(right)) ||
    (isRecord(left) && isRecord(right))
  ) {
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
  if (changes.length >= MAX_DIFF_ENTRIES || valuesEqual(beforeValue, afterValue)) {
    return changes;
  }

  if (depth >= MAX_DIFF_DEPTH) {
    changes.push({ kind: "changed", path, beforeValue, afterValue });
    return changes;
  }

  if (Array.isArray(beforeValue) && Array.isArray(afterValue)) {
    const limit = Math.min(
      Math.max(beforeValue.length, afterValue.length),
      MAX_DIFF_CHILDREN,
    );
    for (let index = 0; index < limit && changes.length < MAX_DIFF_ENTRIES; index += 1) {
      if (index >= beforeValue.length) {
        changes.push({
          kind: "added",
          path: [...path, index],
          beforeValue: undefined,
          afterValue: afterValue[index],
        });
        continue;
      }
      if (index >= afterValue.length) {
        changes.push({
          kind: "removed",
          path: [...path, index],
          beforeValue: beforeValue[index],
          afterValue: undefined,
        });
        continue;
      }
      collectStateChanges(
        beforeValue[index],
        afterValue[index],
        [...path, index],
        depth + 1,
        changes,
      );
    }
    if (changes.length === 0) {
      changes.push({ kind: "changed", path, beforeValue, afterValue });
    }
    return changes;
  }

  if (isRecord(beforeValue) && isRecord(afterValue)) {
    const keys = Array.from(
      new Set([...Object.keys(beforeValue), ...Object.keys(afterValue)]),
    ).sort();
    for (const key of keys.slice(0, MAX_DIFF_CHILDREN)) {
      if (changes.length >= MAX_DIFF_ENTRIES) break;
      if (!(key in beforeValue)) {
        changes.push({
          kind: "added",
          path: [...path, key],
          beforeValue: undefined,
          afterValue: afterValue[key],
        });
        continue;
      }
      if (!(key in afterValue)) {
        changes.push({
          kind: "removed",
          path: [...path, key],
          beforeValue: beforeValue[key],
          afterValue: undefined,
        });
        continue;
      }
      collectStateChanges(
        beforeValue[key],
        afterValue[key],
        [...path, key],
        depth + 1,
        changes,
      );
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

export function topLevelEntries(
  state: Record<string, unknown> | null,
): Array<[string, unknown]> {
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

export { formatPrimitive, pathToString, safeStringify };
