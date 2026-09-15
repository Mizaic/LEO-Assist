/**
 * Static VT: EPR Timeline tab densifies swimlanes and lists activity.
 *
 * Atlas: DI-357A7468 / DO-5D3EA371
 */
import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("EPR timeline layout chrome", () => {
  test("EpisodeSwimlane mounts activity list under pathway lanes", () => {
    const src = readUi("components/patients/EpisodeSwimlane.tsx");
    expect(src).toMatch(/ActivityTimeline/);
    expect(src).toMatch(/epr-timeline-activity/);
    expect(src).toMatch(/EpisodeLaneCard/);
    expect(src).toMatch(/Clinical activity/);
  });

  test("EpisodeLaneCard uses a local time window helper", () => {
    const card = readUi("components/patients/EpisodeLaneCard.tsx");
    const utils = readUi("components/patients/episodeLaneUtils.ts");
    expect(card).toMatch(/episodeTimeWindow/);
    expect(card).toMatch(/epr-episode-lane/);
    expect(utils).toMatch(/export function episodeTimeWindow/);
    expect(card).toMatch(/Referred \$\{fmtDate/);
  });

  test("PatientShell mounts EpisodeSwimlane on the Timeline tab", () => {
    const shell = readUi("components/patients/PatientShell.tsx");
    const body = readUi("components/patients/PatientRecordBody.tsx");
    expect(body).toMatch(/activeTab === "timeline"/);
    expect(body).toMatch(/EpisodeSwimlane/);
    expect(shell).not.toMatch(/ContextRail/);
  });

  test("ActivityTimeline marks encounters, documents, referrals, and SBARs clickable", () => {
    const src = readUi("components/patients/ActivityTimeline.tsx");
    expect(src).toMatch(/onItemClick/);
    expect(src).toMatch(/isClickableType/);
    expect(src).toMatch(/referral:/);
    expect(src).toMatch(/document:/);
    expect(src).toMatch(/sbar:/);
  });

  test("EpisodeSwimlane routes timeline clicks to tab handlers", () => {
    const src = readUi("components/patients/EpisodeSwimlane.tsx");
    expect(src).toMatch(/item_type === "encounter"/);
    expect(src).toMatch(/item_type === "document"/);
    expect(src).toMatch(/item_type === "referral"/);
    expect(src).toMatch(/item_type === "sbar"/);
    expect(src).toMatch(/onDocumentClick/);
    expect(src).toMatch(/onReferralClick/);
    expect(src).toMatch(/onSbarClick/);
  });

  test("PatientShell wires timeline document, referral, and SBAR click-through", () => {
    const nav = readUi("components/patients/useRecordNavigation.ts");
    const body = readUi("components/patients/PatientRecordBody.tsx");
    expect(nav).toMatch(/handleDocumentClick/);
    expect(nav).toMatch(/handleReferralClick/);
    expect(nav).toMatch(/handleSbarClick/);
    expect(nav).toMatch(/assessment:/);
    expect(body).toMatch(/initialDocumentId/);
    expect(body).toMatch(/initialReferralId/);
  });
});
