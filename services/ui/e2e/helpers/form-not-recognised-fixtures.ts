/**
 * Stubbed My work routes for VAL-BC73AA10: a referral paused because its
 * specialty form was not recognised. Does not start a live pipeline.
 *
 * The bundle is a specialty form nobody has taught plus the national e-RS
 * form. The e-RS form was recognised; the specialty form was not.
 */
import type { Page } from "@playwright/test";
import { fulfillJson, stubKnowledgeAdminAuth } from "./surface-forms-fixtures";

export const FNR_TASK_ID = "eqr-fnr-1";
export const FNR_PATIENT_ID = "p-fnr";
export const CLOSEST_FORM = "Sherwood gynae 2WW";
export const FNR_LETTER =
  "--- Document: Lower GI referral ---\n" +
  "Section 1: Patient details\n" +
  "Section 2: Symptoms\n" +
  "Change in bowel habit [X] Rectal bleeding [ ]\n" +
  "--- Document: e-RS Clinical Information ---\n" +
  "Clinical Information Summary\n" +
  "Reason for referral: change in bowel habit";

const RECOGNITION = [
  {
    outcome: "unrecognised",
    title: "Lower GI referral",
    chunk_indexes: [0],
    reason: "form_not_recognised",
    best: {
      fingerprint: "sfh-gynae-2ww-v1",
      form_name: CLOSEST_FORM,
      matched: ["Patient details"],
      missing: [
        "Gynaecological cancer type suspected",
        "Signs and symptoms",
        "Examination findings",
      ],
    },
    runner_up: null,
  },
  {
    outcome: "recognised",
    title: "e-RS Clinical Information",
    chunk_indexes: [1],
    fingerprint: "nhs-ers-clinical-information-v1",
  },
];

export async function stubFormNotRecognisedRoutes(page: Page): Promise<void> {
  await stubKnowledgeAdminAuth(page);
  await page.route("**/api/work/tasks**", (route) =>
    fulfillJson(route, {
      tasks: [
        {
          task_id: "extraction_quality_pause:" + FNR_TASK_ID,
          task_type: "extraction_quality_pause",
          severity: 3,
          summary: "Form not recognised: " + FNR_PATIENT_ID,
          age_days: 0,
          resolve_url: "/admin/knowledge?tab=validation-lab&hitl_task_id=" + FNR_TASK_ID,
          patient_id: FNR_PATIENT_ID,
          episode_id: null,
          failure_kind: "unseen_form",
        },
      ],
      counts_by_source: {
        coding_review: 0,
        safety_net_alert: 0,
        gold_label: 0,
        extraction_quality_pause: 1,
        surface_form_approval: 0,
      },
      limit: 100,
      offset: 0,
    }),
  );
  await page.route("**/api/training/coding-review/grouped**", (route) =>
    fulfillJson(route, { groups: [] }),
  );
  await page.route("**/api/training/surface-form-tasks**", (route) =>
    fulfillJson(route, { items: [] }),
  );
  await page.route(`**/api/operations/extraction-reviews/${FNR_TASK_ID}`, (route) =>
    fulfillJson(route, {
      task_id: FNR_TASK_ID,
      source_text: FNR_LETTER,
      draft_entities: [
        { text: "Change in bowel habit", semantic_tag: "finding", assertion: "present" },
      ],
      document_quality: {
        document_quality_score: 0.3,
        quality_reasons: ["form_not_recognised"],
      },
      form_recognition: RECOGNITION,
      form_fingerprint: "fp-lower-gi",
      reason: "form_not_recognised",
    }),
  );
  await stubTeachRoutes(page);
}

async function stubTeachRoutes(page: Page): Promise<void> {
  await page.route("**/api/admin/orgs", (route) =>
    fulfillJson(route, [{ id: "RK5", name: "Sherwood Forest Hospitals" }]),
  );
  await page.route("**/api/admin/orgs/*/services", (route) =>
    fulfillJson(route, [{ id: "svc-lower-gi", name: "Lower GI 2WW" }]),
  );
  await page.route("**/api/form-schemas/detect", (route) =>
    fulfillJson(route, {
      sections: [
        {
          section_id: "symptoms",
          section_type: "checkbox_multi",
          label: "Symptoms",
          start_pattern: "Section 2",
          items: [],
        },
      ],
    }),
  );
  await page.route(/\/api\/form-schemas(\/fp-lower-gi)?(\?.*)?$/, (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return fulfillJson(route, { schema: null, match: "none", schemas: [] });
  });
}
