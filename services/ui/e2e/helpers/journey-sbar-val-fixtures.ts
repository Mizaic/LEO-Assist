/**
 * Playwright stubs for VAL-03F79BBC (patient journeys and SBAR playback).
 */

import type { Page } from "@playwright/test";

export const PATIENT_ID = "p-val-journey";
export const DOC_TITLE = "Journey referral letter";
export const DOC_BODY = "Two week wait referral to breast clinic.";
export const SOURCE_TAG = "manual_journey";

export const createdBodies: Record<string, unknown>[] = [];

const EPISODE_ID = "ep-val-1";
const SEED_DOC_ID = "doc-seed-1";
const NEW_DOC_ID = "doc-new-1";

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function documentRow(partial: Record<string, unknown>) {
  return {
    document_id: SEED_DOC_ID,
    document_date: "2026-08-01",
    document_type: SOURCE_TAG,
    title: "Seeded journey letter",
    category: "referral",
    text_preview: DOC_BODY,
    full_text: DOC_BODY,
    content_type: "text/markdown",
    original_url: null,
    markdown_url: null,
    episode_id: EPISODE_ID,
    episode_label: "Breast",
    folder_label: "Breast",
    referral_id: "ref-1",
    chunk_count: 1,
    sbar: null,
    ...partial,
  };
}

function patientDetail() {
  return {
    patient_id: PATIENT_ID,
    display_name: "VAL Journey Patient",
    nhs_number: "9990000001",
    gender: "female",
    birth_date: "1970-01-01",
    practice_name: "Oak GP",
    active_alert_count: 0,
    episodes: [
      {
        episode_id: EPISODE_ID,
        condition_type: "breast",
        status: "active",
        referral_date: "2026-08-01",
      },
    ],
  };
}

function completedRun() {
  return {
    run_id: "run-sbar-1",
    status: "completed",
    assessment_id: "assess-doc-1",
    episode_assessment_id: "assess-ep-1",
    rollup_assessment_id: "assess-roll-1",
    error_message: null,
    stage_progress: [],
  };
}

export async function stubJourneyValRoutes(page: Page): Promise<void> {
  createdBodies.length = 0;
  const docs = [documentRow({})];

  await page.route("**/api/proxy/analytics/patients/**", (route) => {
    const url = route.request().url();
    if (url.includes("/documents")) return json(route, docs);
    if (url.includes("/timeline")) return json(route, []);
    if (url.includes("/coded-entities")) return json(route, []);
    if (url.includes("/assessments")) return json(route, []);
    if (url.includes("/alerts")) return json(route, []);
    return json(route, patientDetail());
  });
  await page.route("**/api/patients/**/documents**", async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      createdBodies.push(body);
      docs.unshift(
        documentRow({
          document_id: NEW_DOC_ID,
          title: String(body.title || DOC_TITLE),
          full_text: String(body.markdown_body || DOC_BODY),
          text_preview: String(body.markdown_body || DOC_BODY),
          document_date: "2026-08-22",
          episode_id: String(body.episode_id || EPISODE_ID),
        }),
      );
      return json(route, {
        document_id: NEW_DOC_ID,
        referral_id: "ref-new",
        encounter_id: "enc-new",
        chunk_ids: ["chunk-1"],
      });
    }
    if (method === "PATCH") return json(route, { document_id: NEW_DOC_ID });
    if (method === "DELETE") return json(route, { document_id: NEW_DOC_ID, status: "deleted" });
    return json(route, docs);
  });
  await page.route("**/api/analytics/document-references/**/resolved-chunks", (route) =>
    json(route, { chunks: [{ id: "chunk-1" }] }),
  );
  await page.route("**/api/patients/**/document-runs**", (route) => json(route, completedRun()));
  await page.route("**/api/patients/**/milestone-sbar**", (route) => json(route, completedRun()));
  await page.route("**/api/sbar/assessments/**", (route) =>
    json(route, { situation: "Referral", background: "Letter", assessment: "Review", recommendation: "See clinic" }),
  );
  await page.route("**/api/sdk/widget-token**", (route) =>
    json(route, { widget_token: "val-token" }),
  );
}
