/**
 * Shared paging for clinician record lists.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

export const RECORD_PAGE_SIZE = 20;
export const EPISODE_PAGE_SIZE = 6;

export function visibleSlice<T>(items: T[], shown: number): T[] {
  return items.slice(0, shown);
}

export function remainingCount(total: number, shown: number): number {
  return Math.max(0, total - shown);
}
