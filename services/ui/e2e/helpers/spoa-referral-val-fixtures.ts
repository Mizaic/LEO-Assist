/**
 * Playwright stubs for VAL-9D495A94 (elective SPoA consultant review).
 */

import type { Page } from "@playwright/test";

export const PATIENT_ID = "p-val-spoa";
export const PATIENT_NAME = "VAL SPoA Patient";
export const LETTER_TITLE = "Inbound referral to Gastroenterology";
export const SERVICE_NAME = "Gastroenterology (Hepatology)";
export const PRIMARY_SUPPORT = "Supported by receiving service? no";
export const OTHER_GUIDELINES = "Other guidelines that would support this request";
export const DISPOSITION = "Advisory SPoA disposition: Refer to alternative service";
export const ADVISORY_TEXT =
  "AI-generated summary. Clinician review required before acting on this " +
  "content. This is a decision support aid, it does not replace your " +
  "clinical judgement.";

const ASSESS_ID = "assess-spoa-1";
const EPISODE_ID = "ep-val-spoa";
const LETTER_ID = "doc-spoa-letter";

export const SBAR_MARKDOWN = [
  "## Situation",
  "Inbound referral to Gastroenterology.",
  "",
  "## Background",
  "GP letter for suspected cancer.",
  "",
  "## Assessment",
  "**Receiving service:** Gastroenterology (Hepatology) -- guidelines NG12.",
  "**Supported by receiving service?** no.",
  "No matching guideline rules fired for this patient's coded evidence " +
    "against the receiving service scope.",
  "Reviewed against 3 clinical codes.",
  "",
  "**Other guidelines that would support this request**",
  "- NG12 suspected-cancer colorectal: consider referral to colorectal " +
    "(rule 1.3.4)",
  "",
  "## Recommendation",
  "**Advisory SPoA disposition:** Refer to alternative service.",
  "Receiving service guidelines did not match.",
  "",
  ADVISORY_TEXT,
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
    nhs_number: "9990000002",
    gender: "female",
    birth_date: "1968-03-12",
    practice_name: "Oak GP",
    active_alert_count: 0,
    episodes: [
      {
        episode_id: EPISODE_ID,
        condition_type: "upper_gi",
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
    episode_label: "Upper GI",
    scope: "episode",
    status: "completed",
    created_at: "2026-08-22T12:00:00Z",
    situation: "Inbound referral to Gastroenterology.",
    background: "GP letter for suspected cancer.",
    assessment:
      "**Receiving service:** Gastroenterology (Hepatology) -- guidelines NG12.\n" +
      "**Supported by receiving service?** no.\n" +
      "No matching guideline rules fired for this patient's coded evidence " +
      "against the receiving service scope.\n" +
      "Reviewed against 3 clinical codes.\n\n" +
      "**Other guidelines that would support this request**\n" +
      "- NG12 suspected-cancer colorectal: consider referral to colorectal " +
      "(rule 1.3.4)",
    recommendation:
      "**Advisory SPoA disposition:** Refer to alternative service.\n" +
      "Receiving service guidelines did not match.\n\n" +
      ADVISORY_TEXT,
    content: SBAR_MARKDOWN,
    stt: null,
    stt_evidence: null,
    completeness_failed_count: 0,
    background_parts: null,
    completeness_result_json: null,
    spoa_disposition: "refer_to_alternative_service",
    spoa_disposition_evidence: "Receiving service guidelines did not match.",
  };
}

function letterRow() {
  return {
    document_id: LETTER_ID,
    document_date: "2026-08-22",
    document_type: "referral",
    title: LETTER_TITLE,
    category: "referral",
    text_preview: "Inbound referral to Gastroenterology.",
    full_text: SBAR_MARKDOWN,
    content_type: "text/markdown",
    original_url: null,
    markdown_url: null,
    episode_id: EPISODE_ID,
    episode_label: "Upper GI",
    folder_label: "Upper GI",
    referral_id: "ref-spoa-1",
    chunk_count: 1,
    sbar: null,
  };
}

function widgetPayload() {
  return {
    assessment_id: ASSESS_ID,
    tenant_id: "org-val-spoa",
    generated_at: "2026-08-22T12:00:00Z",
    markdown: SBAR_MARKDOWN,
    background_parts: [],
    guideline_matches: [
      {
        rule_id: "1.3.4",
        name: "NG12 suspected-cancer colorectal",
        strength: "consider",
        guideline_id: "NG12",
        recommendation_verbatim:
          "Consider referral to colorectal for suspected cancer.",
      },
    ],
    completeness_findings: null,
  };
}

export async function stubSpoaReferralValRoutes(page: Page): Promise<void> {
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
    json(route, { widget_token: "val-spoa-token" }),
  );
}
