/**
 * Helpers for grouping recommended procedures as AND / OR /
 * preferred-then-fallback (ease-of-use for NICE "MRI, or CT if MRI
 * not available" patterns).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { STRENGTH_LABELS, friendlyTerm } from "./copy";
import type { ActionGroupMode, RuleAction } from "./types";

export interface ActionDisplayGroup {
  key: string;
  mode: ActionGroupMode;
  /** Indices into the flat actions array, in display order. */
  indices: number[];
}

function freshGroupId(): string {
  return `ag_${Math.random().toString(36).slice(2, 10)}`;
}

function blankSibling(strength: string): RuleAction {
  return {
    criterion: { snomed_concept_id: "", preferred_term: "" },
    strength,
  };
}

function sortIndicesByRank(actions: RuleAction[], indices: number[]): number[] {
  return [...indices].sort((a, b) => {
    const ra = actions[a]?.group_rank ?? a;
    const rb = actions[b]?.group_rank ?? b;
    return ra - rb;
  });
}

/** Collapse a flat actions list into display groups (solo = mode all). */
export function groupActionsForDisplay(actions: RuleAction[]): ActionDisplayGroup[] {
  const seen = new Set<string>();
  const out: ActionDisplayGroup[] = [];
  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    const gid = action.group_id?.trim();
    if (!gid) {
      out.push({ key: `solo-${i}`, mode: "all", indices: [i] });
      continue;
    }
    if (seen.has(gid)) continue;
    seen.add(gid);
    const indices = actions
      .map((a, idx) => (a.group_id === gid ? idx : -1))
      .filter((idx) => idx >= 0);
    const mode = action.group_mode ?? "any";
    out.push({
      key: gid,
      mode,
      indices: sortIndicesByRank(actions, indices),
    });
  }
  return out;
}

function withGroup(
  action: RuleAction,
  groupId: string,
  mode: ActionGroupMode,
  rank: number,
): RuleAction {
  return { ...action, group_id: groupId, group_mode: mode, group_rank: rank };
}

function reRankGroup(actions: RuleAction[], groupId: string): RuleAction[] {
  const members = actions
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => a.group_id === groupId)
    .sort((x, y) => (x.a.group_rank ?? x.i) - (y.a.group_rank ?? y.i));
  if (members.length <= 1) {
    return actions.map((a) =>
      a.group_id === groupId
        ? { ...a, group_id: undefined, group_mode: undefined, group_rank: undefined }
        : a,
    );
  }
  const rankByIndex = new Map(members.map((m, rank) => [m.i, rank]));
  return actions.map((a, i) =>
    rankByIndex.has(i)
      ? { ...a, group_rank: rankByIndex.get(i), group_mode: a.group_mode }
      : a,
  );
}

/**
 * Insert a blank procedure as preferred-fallback after ``afterIndex``.
 * Returns the new list and the index of the blank row.
 */
export function addFallbackAfter(
  actions: RuleAction[],
  afterIndex: number,
): { actions: RuleAction[]; newIndex: number } {
  const anchor = actions[afterIndex];
  if (!anchor) return { actions, newIndex: afterIndex };
  const groupId = anchor.group_id?.trim() || freshGroupId();
  const mode: ActionGroupMode = "preferred_fallback";
  const members = actions
    .map((a, i) => ({ a, i }))
    .filter(({ a, i }) =>
      a.group_id === groupId || i === afterIndex,
    );
  const nextRank =
    Math.max(
      0,
      ...members.map(({ a, i }) =>
        i === afterIndex || a.group_id === groupId ? (a.group_rank ?? 0) : 0,
      ),
    ) + 1;
  const next = actions.map((a, i) => {
    if (i === afterIndex) return withGroup(a, groupId, mode, a.group_rank ?? 0);
    if (a.group_id === groupId) return { ...a, group_mode: mode };
    return a;
  });
  const insertAt = afterIndex + 1;
  next.splice(
    insertAt,
    0,
    withGroup(blankSibling(anchor.strength), groupId, mode, nextRank),
  );
  return { actions: reRankGroup(next, groupId), newIndex: insertAt };
}

/**
 * Insert a blank procedure as an either/or alternative after ``afterIndex``.
 */
export function addOrAlternativeAfter(
  actions: RuleAction[],
  afterIndex: number,
): { actions: RuleAction[]; newIndex: number } {
  const anchor = actions[afterIndex];
  if (!anchor) return { actions, newIndex: afterIndex };
  const groupId = anchor.group_id?.trim() || freshGroupId();
  const mode: ActionGroupMode = "any";
  const nextRank =
    Math.max(
      0,
      ...actions
        .filter((a) => a.group_id === groupId)
        .map((a) => a.group_rank ?? 0),
      anchor.group_rank ?? 0,
    ) + 1;
  const next = actions.map((a, i) => {
    if (i === afterIndex) return withGroup(a, groupId, mode, a.group_rank ?? 0);
    if (a.group_id === groupId) return { ...a, group_mode: mode };
    return a;
  });
  const insertAt = afterIndex + 1;
  next.splice(
    insertAt,
    0,
    withGroup(blankSibling(anchor.strength), groupId, mode, nextRank),
  );
  return { actions: reRankGroup(next, groupId), newIndex: insertAt };
}

/** Remove one action and dissolve a group that falls below 2 members. */
export function removeActionKeepingGroups(
  actions: RuleAction[],
  index: number,
): RuleAction[] {
  if (actions.length <= 1) return actions;
  const removed = actions[index];
  const next = actions.filter((_, i) => i !== index);
  if (!removed?.group_id) return next;
  return reRankGroup(next, removed.group_id);
}

/** Plain-English caption for a display group. */
export function actionGroupCaption(mode: ActionGroupMode): string | null {
  if (mode === "preferred_fallback") {
    return "Prefer the first. If it is not available, suggest the next.";
  }
  if (mode === "any") {
    return "Suggest either of these (either is fine).";
  }
  return null;
}

/** Rank label inside a preferred_fallback or any group. */
export function actionGroupRankLabel(
  mode: ActionGroupMode,
  rankIndex: number,
): string | null {
  if (mode === "preferred_fallback") {
    return rankIndex === 0 ? "1st choice" : "If not available";
  }
  if (mode === "any") {
    return rankIndex === 0 ? "Option" : "Or";
  }
  return null;
}

function procedurePhrase(action: RuleAction): string {
  return friendlyTerm(action.criterion?.preferred_term) || "no procedure picked yet";
}

function strengthPhrase(strength: string): string {
  return (
    STRENGTH_LABELS.find((o) => o.value === strength)?.label ??
    "Not specified yet"
  );
}

/**
 * One plain-English recap line per display group for the live preview.
 * CDS suggests the chain; it does not pick from local availability.
 */
export function formatActionGroupRecapLines(actions: RuleAction[]): string[] {
  return groupActionsForDisplay(actions).map((group) => {
    const members = group.indices.map((i) => actions[i]).filter(Boolean);
    if (members.length === 0) return "No procedure picked yet.";
    if (group.mode === "preferred_fallback" && members.length > 1) {
      const first = members[0];
      const rest = members.slice(1);
      const head =
        `If this rule matches: ${strengthPhrase(first.strength)} - ` +
        `${procedurePhrase(first)}.`;
      const tail = rest
        .map(
          (a) =>
            `If that is not available: ${strengthPhrase(a.strength)} - ` +
            `${procedurePhrase(a)}.`,
        )
        .join(" ");
      return `${head} ${tail}`;
    }
    if (group.mode === "any" && members.length > 1) {
      const parts = members.map(
        (a) => `${strengthPhrase(a.strength)} - ${procedurePhrase(a)}`,
      );
      return `If this rule matches: ${parts.join(", or ")}.`;
    }
    const a = members[0];
    return (
      `If this rule matches: ${strengthPhrase(a.strength)} - ` +
      `${procedurePhrase(a)}.`
    );
  });
}
