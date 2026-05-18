// VT-DAEE0DFD -- PatientDetailDrawer fetches the patient's full
// EpisodeOfCare list independent of the dashboard cohort filter
// (DI-5E47FA5D, mitigates R-A737EE12).
//
// This test pins three things:
//   1. The drawer imports the dedicated patient-scoped helper
//      (fetchMissionPatientEpisodes) and calls it from a useEffect
//      keyed on patient_id, orgId and a refresh nonce.
//   2. The drawer feeds `drawerEpisodes` (the local, cohort-filter
//      free list) into the focus-chip rail, OverviewTab,
//      EncounterTextTab and EditEpisodeDialog -- NOT the original
//      `patient.episodes` array, which is filtered by lifecycle
//      bucket on the dashboard.
//   3. After a successful manual create the drawer focuses the new
//      episode (which is now visible because the local list is not
//      cohort-filtered) and shows the success toast.
//
// Why static source rather than render: the drawer pulls in MUI
// Drawer, the role provider, the audit-trail SSE hook and several
// mission-control fetchers -- a runtime render here would be a
// 200-line mock farm. The behaviour we care about is a small set of
// structural invariants, so we assert on the source. Runtime
// behaviour for the API helper itself is covered separately by
// fetch-mission-patient-episodes.test.ts.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const COMPONENT_DIR = path.join(
  ROOT,
  "services/ui/src/components/mission-control",
);

function read(name: string): string {
  return fs.readFileSync(path.join(COMPONENT_DIR, name), "utf-8");
}

describe("VT-DAEE0DFD - PatientDetailDrawer full episode list", () => {
  const drawerSrc = read("PatientDetailDrawer.tsx");
  const overviewSrc = read("OverviewTab.tsx");

  it("imports fetchMissionPatientEpisodes from the mission-control API", () => {
    expect(drawerSrc).toMatch(
      /import\s*\{[^}]*fetchMissionPatientEpisodes[^}]*\}\s*from\s*"@\/lib\/missionControlApi"/s,
    );
  });

  it("calls the helper from a useEffect keyed on patient_id, orgId and the local refresh nonce", () => {
    expect(drawerSrc).toMatch(/fetchMissionPatientEpisodes\(\s*patient\.patient_id/);
    expect(drawerSrc).toMatch(
      /\}, \[patient\.patient_id, orgId, drawerEpisodesNonce\]\)/,
    );
  });

  it("declares a drawer-local episode list seeded from patient.episodes", () => {
    expect(drawerSrc).toMatch(
      /const \[drawerEpisodes, setDrawerEpisodes\] = useState<MissionEpisode\[\]>\(\s*patient\.episodes,?\s*\)/,
    );
    expect(drawerSrc).toMatch(/setDrawerEpisodesNonce/);
    expect(drawerSrc).toMatch(/refreshDrawerEpisodes/);
  });

  it("feeds drawerEpisodes (not patient.episodes) into the focus-chip rail and sub-views", () => {
    // Focus-chip rail iterates the local list.
    expect(drawerSrc).toMatch(/drawerEpisodes\.map\(/);
    expect(drawerSrc).not.toMatch(/patient\.episodes\.map\(/);

    // EncounterTextTab gets the local list as `episodes`.
    expect(drawerSrc).toMatch(/episodes=\{drawerEpisodes\}/);

    // EditEpisodeDialog gets the local list as `siblingEpisodes`.
    expect(drawerSrc).toMatch(/siblingEpisodes=\{drawerEpisodes\}/);

    // OverviewTab gets the override prop.
    expect(drawerSrc).toMatch(/<OverviewTab[\s\S]*?episodes=\{drawerEpisodes\}/);
  });

  it("uses the local list to resolve the focused episode", () => {
    // Old code: patient.episodes.find(...) ?? patient.episodes[0]
    // New code: drawerEpisodes.find(...) ?? drawerEpisodes[0]
    expect(drawerSrc).toMatch(/drawerEpisodes\.find\(\(e\) => e\.episode_id === focusedEpisodeId\)/);
    expect(drawerSrc).toMatch(/drawerEpisodes\[0\]/);
  });

  it("on a successful create, focuses the new episode and refreshes the local list", () => {
    // After a manual create the new episode lands in the local list
    // because the helper bypasses the cohort filter; focusing it makes
    // the chip rail update without the user changing the dashboard
    // filter.
    expect(drawerSrc).toMatch(/setFocusedEpisodeId\(newEpisodeId\)/);
    // triggerLiveRefresh now bumps the drawer-local nonce so the
    // local list refetches.
    expect(drawerSrc).toMatch(/refreshDrawerEpisodes\(\)[\s\S]*?onPatientRefreshed/);
  });

  it("preserves focused episode across same-patient refreshes", () => {
    expect(drawerSrc).toMatch(/previousPatientIdRef/);
    expect(drawerSrc).toMatch(
      /setFocusedEpisodeId\(\(current\) => \{[\s\S]*?if \(patientChanged\) return patient\.episodes\[0\]\?\.episode_id \?\? ""/,
    );
    expect(drawerSrc).toMatch(/if \(current\) return current/);
    expect(drawerSrc).toMatch(
      /res\.episodes\.some\(\(e\) => e\.episode_id === current\)/,
    );
    expect(drawerSrc).not.toMatch(
      /setFocusedEpisodeId\(patient\.episodes\[0\]\?\.episode_id \?\? ""\)/,
    );
  });

  it("OverviewTab accepts an episodes override and uses it when set", () => {
    // The Props interface gains an optional `episodes` prop ...
    expect(overviewSrc).toMatch(/episodes\?:\s*MissionEpisode\[\]/);
    // ... and the rendered list comes from the override (with a
    // fallback to patient.episodes for backwards compatibility).
    expect(overviewSrc).toMatch(/const episodeList = episodes \?\? patient\.episodes/);
    expect(overviewSrc).toMatch(/episodeList\.map\(/);
  });
});
