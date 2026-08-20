/**
 * Stubbed Operations review routes for VAL-9D7630B3.
 * Does not start a live pipeline.
 */

import type { Page } from "@playwright/test";
import { fulfillJson } from "./surface-forms-fixtures";

export const VAL_TASK_ID = "eqr-val-1";
export const VAL_LETTER_TEXT =
  "Section A: Gynaecological Cancer type suspected\nCervix [X]\npolyp noted";

export type CompletePayload = {
  task_id?: string;
  reviewed_entities?: Array<{ text?: string }>;
};

export async function stubExtractionQualityReviewRoutes(
  page: Page,
  completeCalls: CompletePayload[],
): Promise<void> {
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
          reason: "unknown_form_template",
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
  await page.route(`**/api/operations/extraction-reviews/${VAL_TASK_ID}`, (route) => {
    if (route.request().method() !== "GET") {
      return route.fallback();
    }
    return fulfillJson(route, {
      task_id: VAL_TASK_ID,
      source_text: VAL_LETTER_TEXT,
      draft_entities: [{ text: "Cervix" }],
      document_quality: {
        document_quality_score: 0.31,
        quality_reasons: ["unknown_form_template"],
      },
    });
  });
}
