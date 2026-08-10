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

  test("PatientShell hides left episode rail on Timeline tab", () => {
    const src = readUi("components/patients/PatientShell.tsx");
    expect(src).toMatch(/activeTab === "timeline"/);
    expect(src).toMatch(/EpisodeSwimlane/);
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
    const src = readUi("components/patients/PatientShell.tsx");
    expect(src).toMatch(/handleDocumentClick/);
    expect(src).toMatch(/handleReferralClick/);
    expect(src).toMatch(/handleSbarClick/);
    expect(src).toMatch(/assessment:/);
    expect(src).toMatch(/initialDocumentId/);
    expect(src).toMatch(/initialReferralId/);
  });
});
