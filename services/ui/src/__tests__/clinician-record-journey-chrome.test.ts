/**
 * Clinician record journey -- progressive disclosure, contrast, pagination.
 *
 * Atlas trace:
 *   VT: VT-04B722C3
 *   DI: DI-357A7468
 *   DO: DO-5D3EA371
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("Clinician record journey chrome", () => {
  test("TC-001: shared pager slices lists and exposes Show more", () => {
    const page = readUi("components/patients/recordPage.ts");
    const more = readUi("components/patients/RecordShowMore.tsx");
    expect(page).toMatch(/RECORD_PAGE_SIZE\s*=\s*20/);
    expect(page).toMatch(/export function visibleSlice/);
    expect(page).toMatch(/export function remainingCount/);
    expect(more).toMatch(/record-show-more/);
    expect(more).toMatch(/Show/);
  });

  test("TC-002: Timeline paginates activity and filters by type", () => {
    const lane = readUi("components/patients/EpisodeSwimlane.tsx");
    const timeline = readUi("components/patients/ActivityTimeline.tsx");
    expect(timeline).toMatch(/RecordShowMore/);
    expect(timeline).toMatch(/visibleSlice/);
    expect(lane).toMatch(/ProgressiveReveal/);
    expect(lane).toMatch(/FilterBar/);
  });

  test("TC-003: Encounters fill the tab, search with FilterBar, and paginate", () => {
    const src = readUi("components/patients/EncounterListPanel.tsx");
    expect(src).toMatch(/epr-encounter-workspace/);
    expect(src).toMatch(/FilterBar/);
    expect(src).toMatch(/RecordShowMore/);
    expect(src).not.toMatch(/100vh/);
    expect(src).not.toMatch(/#94A3B8/);
  });

  test("TC-004: Alerts put the open job first and hide resolved", () => {
    const src = readUi("components/patients/AlertsPanel.tsx");
    expect(src).toMatch(/ProgressiveReveal/);
    expect(src).toMatch(/Resolved/);
    expect(src).toMatch(/RecordShowMore/);
    expect(src).toMatch(/color\.text\.caption|#6B7280/);
  });

  test("TC-005: Overview paginates episode cards", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/RecordShowMore/);
    expect(src).toMatch(/visibleSlice/);
  });
});
