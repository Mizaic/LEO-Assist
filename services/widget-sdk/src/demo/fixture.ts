/**
 * Synthetic SBAR payload for integrator demos and local VT fixtures.
 *
 * No real patient data. Used by the CDN demo card (/demo/) and the
 * iframe ?demo=1 mode so hosts can verify CDN + widget behaviour
 * before wiring auth and live assessments.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")
 */
import type { SbarAssessmentPayload } from "../data/types";
import { configureFetcher, configureSourceTextFetcher } from "../data/fetcher";

export const DEMO_ASSESSMENT_ID = "ass-2WW-demo";

export const DEMO_SBAR_PAYLOAD: SbarAssessmentPayload = {
  assessmentId: DEMO_ASSESSMENT_ID,
  tenantId: "tenant-demo",
  patientReferenceLabel: "Mr Demo Patient (NHS 999 999 9999)",
  generatedAt: "2026-04-20T15:00:00Z",
  markdown:
    "# SBAR\n## Situation\n2WW lower GI referral; 65y M with new IDA.\n" +
    "## Background\n6 weeks fatigue, MCV 78, ferritin 8.\n" +
    "## Assessment\nIron-deficiency anaemia; rule out colorectal cancer.\n" +
    "## Recommendation\nUrgent colonoscopy within 2 weeks.\n",
  backgroundParts: [
    {
      index: 1,
      total: 1,
      recordCount: 3,
      recordRange: [1, 3],
      sourceIds: ["enc-DEMO-001", "enc-DEMO-002", "enc-DEMO-003"],
      status: "completed",
    },
  ],
};

export function configureDemoFetcher(assessmentId?: string): void {
  const id = assessmentId?.trim() || DEMO_ASSESSMENT_ID;
  configureFetcher(async () => ({
    ...DEMO_SBAR_PAYLOAD,
    assessmentId: id,
  }));
  configureSourceTextFetcher(async ({ sourceId }) => ({
    id: sourceId,
    type: "Encounter",
    label: sourceId,
    text:
      "Demo record text. In production this dialog shows the exact " +
      "record text the LLM used to write this part of the Background " +
      `section for source ${sourceId}.`,
  }));
}
