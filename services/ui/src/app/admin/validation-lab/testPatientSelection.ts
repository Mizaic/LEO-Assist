/**
 * Selection helpers for Validation Lab test-patient multi-select.
 *
 * Atlas: DI-43E908C6 / VT-3959DFB3 / DO-158BE606
 */

export function toggleId(selected: Set<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

export function clearSelection(): Set<string> {
  return new Set();
}

/** Keep only ids that still exist in the current case list. */
export function pruneSelection(
  selected: Set<string>,
  existingIds: string[],
): Set<string> {
  const allowed = new Set(existingIds);
  const next = new Set<string>();
  for (const id of selected) {
    if (allowed.has(id)) next.add(id);
  }
  return next;
}

export function allSelected(ids: string[], selected: Set<string>): boolean {
  return ids.length > 0 && ids.every((id) => selected.has(id));
}

export function someSelected(ids: string[], selected: Set<string>): boolean {
  return ids.some((id) => selected.has(id));
}
