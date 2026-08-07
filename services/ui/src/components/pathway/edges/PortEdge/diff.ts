/**
 * Re-exports shared diff helpers; Pathway-specific helpers remain here.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
export {
  collectStateChanges,
  getValueAtPath,
  valuesEqual,
  toneForChange,
  labelForChange,
  topLevelEntries,
  type PathSegment,
  type SearchMatch,
  type StateChange,
  type StateChangeKind,
} from "@/lib/pipelineStateDiff";

import {
  MAX_DIFF_CHILDREN,
  PRIORITY_KEYS,
  type PathSegment,
  type SearchMatch,
  formatPrimitive,
  isRecord,
  pathToString,
} from "./utils";
import { getValueAtPath } from "@/lib/pipelineStateDiff";

export function resolveInspectablePath(root: unknown, path: PathSegment[]): PathSegment[] {
  for (let index = path.length; index > 0; index -= 1) {
    const candidate = path.slice(0, index);
    if (getValueAtPath(root, candidate) !== undefined) return candidate;
  }
  return [];
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
    value.slice(0, 50).forEach((item, index) =>
      collectSearchMatches(item, query, [...path, index], matches),
    );
    return matches;
  }

  if (isRecord(value)) {
    Object.entries(value)
      .slice(0, 100)
      .forEach(([key, child]) => {
        if (matches.length >= 40) return;
        collectSearchMatches(child, query, [...path, key], matches);
      });
  }

  return matches;
}

export function getMeaningfulHighlights(
  entries: Array<[string, unknown]>,
): Array<[string, unknown]> {
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
    Object.keys(value)
      .slice(0, 4)
      .forEach((key) => expanded.add(pathToString([rootLabel, key])));
  }
  return expanded;
}

export function expandAncestors(path: PathSegment[]): Set<string> {
  const expanded = new Set<string>();
  for (let i = 1; i <= path.length; i += 1) expanded.add(pathToString(path.slice(0, i)));
  return expanded;
}
