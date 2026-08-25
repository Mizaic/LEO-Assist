/**
 * Stubbed Operations review routes for VAL-9D7630B3.
 * Does not start a live pipeline.
 */

import type { Page } from "@playwright/test";
import { fulfillJson } from "./surface-forms-fixtures";
import { stubPhraseMappingInbox } from "./work-task-dialog-fixtures";

export const VAL_TASK_ID = "eqr-val-1";
export const VAL_LETTER_TEXT =
  "Section A: Gynaecological Cancer type suspected\n" +
  "Ovary [ ] Cervix [X] Endometrium [ ]\n" +
  "Section B: Signs/symptoms\n" +
  "polyp noted\n" +
  "BMI: 20.2 Kg/m2";

export type CompletePayload = {
  task_id?: string;
  reviewed_entities?: Array<{ text?: string; semantic_tag?: string }>;
};

export async function stubExtractionQualityReviewRoutes(
  page: Page,
  completeCalls: CompletePayload[],
): Promise<void> {
  await page.route("**/api/work/tasks**", (route) =>
    fulfillJson(route, {
      tasks: [
        {
          task_id: "extraction_quality_pause:" + VAL_TASK_ID,
          task_type: "extraction_quality_pause",
          severity: 3,
          summary: "Paused extraction: p-val",
          age_days: 0,
          resolve_url:
            "/admin/knowledge?tab=validation-lab&hitl_task_id=" + VAL_TASK_ID,
          patient_id: "p-val",
          episode_id: null,
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
  await page.route("**/api/operations/tasks**", (route) => {
    if (route.request().method() !== "GET") {
      return route.fallback();
    }
    return fulfillJson(route, {
      tasks: [
        {
          task_id: VAL_TASK_ID,
          task_type: "extraction_quality_review",
          episode_id: "",
          patient_id: "p-val",
          status: "pending",
          priority: 10,
          reason: "few_shot_ood,unknown_form_template,wrapper_admin_only",
        },
      ],
    });
  });
  await page.route("**/api/operations/extraction-reviews/complete", async (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback();
    }
    completeCalls.push(
      (route.request().postDataJSON() as CompletePayload) || {},
    );
    return fulfillJson(route, { resume_once: true, already_resumed: false });
  });
  await stubPhraseMappingInbox(page, {
    phrase_key: "cervix",
    sample_span: "Cervix",
    sample_sentence: VAL_LETTER_TEXT,
    extracted_tag: "finding",
    last_best_term: "",
  });
  await page.route(`**/api/operations/extraction-reviews/${VAL_TASK_ID}`, (route) => {
    if (route.request().method() !== "GET") {
      return route.fallback();
    }
    return fulfillJson(route, {
      task_id: VAL_TASK_ID,
      source_text: VAL_LETTER_TEXT,
      draft_entities: [
        { text: "Cervix", semantic_tag: "body_structure", assertion: "present" },
        { text: "polyp noted", semantic_tag: "finding", assertion: "present" },
        { text: "BMI: 20.2 Kg/m2", semantic_tag: "observable", assertion: "present" },
      ],
      document_quality: {
        document_quality_score: 0.05,
        quality_reasons: [
          "few_shot_ood",
          "unknown_form_template",
          "wrapper_admin_only",
        ],
      },
    });
  });
}
