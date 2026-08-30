/**
 * Playwright stubs for VAL-AB092472 (1.5.13 first-presentation Assessment).
 */

import type { Page } from "@playwright/test";

export const PATIENT_ID = "p-val-1513";
export const PATIENT_NAME = "VAL 1.5.13 Patient";
export const UBRN = "000481914514";
export const LETTER_TITLE = `Referral ${UBRN}`;
export const RULE_LINE = "NG12 1.5.13 consider ultrasound";
export const FIRST_PRESENTATION_ASKED =
  "The guideline also asks for a first presentation of this symptom.";
export const COULD_NOT_CONFIRM = "We could not confirm that from this letter.";
export const SCAN_STILL_OFFERED =
  "We have still offered the scan so a possible cancer is not missed.";
export const NOT_ON_FIT_LIST =
  "This letter is not on a missing faecal immunochemical test (FIT) list.";

const ASSESS_ID = "assess-1513-1";
const EPISODE_ID = "ep-val-1513";
const LETTER_ID = "doc-1513-letter";

export const SBAR_MARKDOWN = [
  "## Situation",
  `Referral Unique Booking Reference Number ${UBRN}.`,
  "",
  "## Background",
  "GP letter for suspected gynaecological cancer.",
  "",
  "## Assessment",
  `- **${RULE_LINE}** _(strength: consider)_`,
  "  - **Recommendation:** Consider ultrasound of the abdomen and pelvis.",
  `  - ${FIRST_PRESENTATION_ASKED} ${COULD_NOT_CONFIRM} ${SCAN_STILL_OFFERED} Please check whether this is a first episode.`,
  "",
  "## Recommendation",
  "Consider ultrasound of the abdomen and pelvis.",
  NOT_ON_FIT_LIST,
  "",
  "AI-generated summary. Clinician review required before acting on this content.",
].join("\n");

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function patientDetail() {
  return {
    patient_id: PATIENT_ID,
    display_name: PATIENT_NAME,
    nhs_number: "9990001513",
    gender: "female",
    birth_date: "1962-04-08",
    practice_name: "Oak GP",
    active_alert_count: 0,
    episodes: [
      {
        episode_id: EPISODE_ID,
        condition_type: "gynaecology",
        status: "active",
        referral_date: "2026-08-01",
      },
    ],
  };
}

function assessmentRow() {
  return {
    assessment_id: ASSESS_ID,
    episode_id: EPISODE_ID,
    episode_label: "Gynaecology",
    scope: "episode",
    status: "completed",
    created_at: "2026-08-22T12:00:00Z",
    situation: `Referral Unique Booking Reference Number ${UBRN}.`,
    background: "GP letter for suspected gynaecological cancer.",
    assessment:
      `- **${RULE_LINE}** _(strength: consider)_\n` +
      "  - **Recommendation:** Consider ultrasound of the abdomen and pelvis.\n" +
      `  - ${FIRST_PRESENTATION_ASKED} ${COULD_NOT_CONFIRM} ${SCAN_STILL_OFFERED} Please check whether this is a first episode.`,
    recommendation:
      "Consider ultrasound of the abdomen and pelvis.\n" + NOT_ON_FIT_LIST,
    content: SBAR_MARKDOWN,
    stt: null,
    stt_evidence: null,
    completeness_failed_count: 0,
    background_parts: null,
    completeness_result_json: null,
  };
}

function letterRow() {
  return {
    document_id: LETTER_ID,
    document_date: "2026-08-22",
    document_type: "referral",
    title: LETTER_TITLE,
    category: "referral",
    text_preview: `Referral Unique Booking Reference Number ${UBRN}.`,
    full_text: SBAR_MARKDOWN,
    content_type: "text/markdown",
    original_url: null,
    markdown_url: null,
    episode_id: EPISODE_ID,
    episode_label: "Gynaecology",
    folder_label: "Gynaecology",
    referral_id: UBRN,
    chunk_count: 1,
    sbar: null,
  };
}

function widgetPayload() {
  return {
    assessment_id: ASSESS_ID,
    tenant_id: "org-val-1513",
    generated_at: "2026-08-22T12:00:00Z",
    markdown: SBAR_MARKDOWN,
    background_parts: [],
    guideline_matches: [
      {
        rule_id: "1.5.13",
        name: RULE_LINE,
        strength: "consider",
        guideline_id: "NG12",
        recommendation_verbatim: "Consider ultrasound of the abdomen and pelvis.",
        investigation_policy: null,
        investigation_status: null,
      },
    ],
    completeness_findings: null,
  };
}

export async function stubSoftGate1513ValRoutes(page: Page): Promise<void> {
  await page.route("**/auth/session", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return json(route, {
      user: { email: "e2e.clinician@example.com", name: "E2E Clinician" },
      isPlatformAdmin: true,
      organizations: [
        {
          id: "org-val-1513",
          name: "E2E Test Organisation",
          odsCode: "E2E",
          shortName: "E2E",
          type: "test",
        },
      ],
      idleTimeoutMinutes: 30,
      selected_role: "administrator",
      allowed_roles: ["administrator", "triage_clinician"],
      needs_role_choice: false,
      density_preference: "comfortable",
    });
  });
  await page.route("**/api/proxy/analytics/patients/**", (route) => {
    const url = route.request().url();
    if (url.includes("/documents")) return json(route, [letterRow()]);
    if (url.includes("/assessments")) return json(route, [assessmentRow()]);
    if (url.includes("/timeline")) return json(route, []);
    if (url.includes("/coded-entities")) return json(route, []);
    if (url.includes("/alerts")) return json(route, []);
    return json(route, patientDetail());
  });
  await page.route("**/api/sbar/assessments/**", (route) =>
    json(route, assessmentRow()),
  );
  await page.route("**/sdk/sbar/**", (route) => json(route, widgetPayload()));
  await page.route("**/api/sdk/widget-token**", (route) =>
    json(route, { widget_token: "val-1513-token" }),
  );
  await page.route("**/terminology/guidelines/missing-fit-list", (route) =>
    json(route, { organization_id: "org-val-1513", referrals: [] }),
  );
}
