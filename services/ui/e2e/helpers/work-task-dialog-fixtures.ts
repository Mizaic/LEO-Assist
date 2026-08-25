/**
 * Stubbed My work queue and task dialogs for the walkthrough.
 * Does not start a live pipeline.
 */
import type { Page } from "@playwright/test";
import { fulfillJson, stubKnowledgeAdminAuth } from "./surface-forms-fixtures";

export const CODING_REVIEW_ID = "rev-hba1c";
export const SURFACE_TASK_ID = "sf-t2dm";
export const GOLD_CANDIDATE_ID = "cand-1";
export const SAFETY_ALERT_ID = "alert-1";
export const EXTRACT_TASK_ID = "eqr-walk-1";
export const PHRASE_PUBLISH_KEY = "raised-hba1c";

const LETTER =
  "Referral for suspected diabetes. Raised HbA1c noted. Family history of type 2 diabetes.";

export async function stubWorkTaskDialogRoutes(page: Page): Promise<void> {
  await stubKnowledgeAdminAuth(page);
  await page.route("**/api/work/tasks**", (route) =>
    fulfillJson(route, {
      tasks: [
        {
          task_id: "coding_review:" + CODING_REVIEW_ID,
          task_type: "coding_review",
          severity: 2,
          summary: "Check code for raised HbA1c",
          age_days: 1,
          resolve_url: "/admin/operations/reviews",
          patient_id: "p-1",
          episode_id: null,
        },
        {
          task_id: "extraction_quality_pause:" + EXTRACT_TASK_ID,
          task_type: "extraction_quality_pause",
          severity: 3,
          summary: "Paused extraction: p-1",
          age_days: 0,
          resolve_url: "/admin/knowledge?tab=validation-lab",
          patient_id: "p-1",
          episode_id: null,
        },
        {
          task_id: "surface_form_approval:" + SURFACE_TASK_ID,
          task_type: "surface_form_approval",
          severity: 2,
          summary: "Check mapping for T2DM",
          age_days: 2,
          resolve_url: "/admin/knowledge?tab=surface-forms",
          patient_id: null,
          episode_id: null,
        },
        {
          task_id: "gold_label:" + GOLD_CANDIDATE_ID,
          task_type: "gold_label",
          severity: 2,
          summary: "Review gold label",
          age_days: 3,
          resolve_url: "/admin/knowledge",
          patient_id: null,
          episode_id: null,
        },
        {
          task_id: "safety_net_alert:" + SAFETY_ALERT_ID,
          task_type: "safety_net_alert",
          severity: 4,
          summary: "Safety alert for p-1",
          age_days: 0,
          resolve_url: "/care/patients/p-1",
          patient_id: "p-1",
          episode_id: "ep-1",
          failure_kind: "safety_flag",
        },
        {
          task_id: "phrase_publish:" + PHRASE_PUBLISH_KEY,
          task_type: "phrase_publish",
          severity: 3,
          summary: "Change to publish: raised HbA1c",
          age_days: 1,
          resolve_url: "/work",
          patient_id: null,
          episode_id: null,
          failure_kind: "change_to_publish",
          draft_author: "engineer@example.com",
          draft_action: "map",
        },
      ],
      counts_by_source: {
        coding_review: 1,
        safety_net_alert: 1,
        gold_label: 1,
        extraction_quality_pause: 1,
        surface_form_approval: 1,
        phrase_publish: 1,
      },
      limit: 100,
      offset: 0,
    }),
  );
  await page.route("**/api/training/coding-review/grouped**", (route) =>
    fulfillJson(route, {
      groups: [
        {
          entity_text: "raised HbA1c",
          entity_label: "finding",
          review_count: 3,
          best_score: 0.62,
          sample_review_id: CODING_REVIEW_ID,
          any_uncoded: true,
          suggested_semantic_tag: "finding",
          sample_encounter_text: LETTER,
          decision_tier: 2,
          tier_reason: "uncertain",
          tier_decision: "review",
          suggested_label: null,
          tag_mismatch_delta: null,
        },
      ],
    }),
  );
  await page.route("**/api/training/surface-form-tasks**", (route) =>
    fulfillJson(route, {
      items: [
        {
          task_id: SURFACE_TASK_ID,
          entity_text: "T2DM",
          current_concept: "",
          current_term: "",
          suggested_concept: "44054006",
          suggested_term: "Type 2 diabetes mellitus",
          confidence: 0.81,
          source: "manual",
        },
      ],
    }),
  );
  await page.route("**/api/training/gold-labels**", (route) =>
    fulfillJson(route, {
      label_id: "gold-1",
      text: "Raised HbA1c. Family history of type 2 diabetes.",
      entities_json: JSON.stringify([
        { text: "Raised HbA1c", label: "finding", assertion: "present" },
      ]),
      quality_score: 0.7,
      source: "training",
      verified_by: null,
      verified_at: null,
      candidate_id: GOLD_CANDIDATE_ID,
      updated_at: "2026-08-24T12:00:00Z",
      items: [],
      total: 0,
    }),
  );
  await page.route(`**/api/operations/extraction-reviews/${EXTRACT_TASK_ID}`, (route) =>
    fulfillJson(route, {
      task_id: EXTRACT_TASK_ID,
      source_text: LETTER,
      draft_entities: [{ text: "raised HbA1c", semantic_tag: "finding", assertion: "present" }],
      document_quality: {
        document_quality_score: 0.31,
        quality_reasons: ["unknown_form_template"],
      },
      reason: "low_document_quality",
    }),
  );
  await stubPhraseMappingInbox(page, {
    phrase_key: "raised hba1c",
    sample_span: "raised HbA1c",
    sample_sentence: LETTER,
    extracted_tag: "finding",
    last_best_term: "Hemoglobin A1c measurement",
  });
  await page.route("**/api/training/post-processor-rules", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(route, { rule_id: "rule-1", status: "created" });
    }
    return fulfillJson(route, { items: [] });
  });
  await page.route("**/api/training/context-rules", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(route, { rule_id: "ctx-1", status: "created" });
    }
    return fulfillJson(route, { items: [] });
  });
  await page.route("**/api/operations/extraction-reviews/few-shot", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(route, {
        deidentified: true,
        category: "missed_span",
        input: "Missed polyp noted in clinic.",
        output: "{\"terms\":[{\"text\":\"polyp\"}]}",
      });
    }
    return fulfillJson(route, {});
  });
  await page.route("**/api/terminology/search**", (route) =>
    fulfillJson(route, [
      {
        snomed_concept_id: "43396009",
        term: "Hemoglobin A1c measurement (procedure)",
        semantic_tag: "procedure",
        score: 0.91,
      },
    ]),
  );
  await page.route("**/api/terminology/surface-forms/upsert-mapping", (route) =>
    fulfillJson(route, {
      normalized: "raised hba1c",
      form: "raised HbA1c",
      concept_id: "43396009",
      concept_fsn: "Hemoglobin A1c measurement (procedure)",
    }),
  );
  await page.route("**/api/training/coding-review/**/ignore", (route) =>
    fulfillJson(route, { status: "ignored" }),
  );
}

export async function stubPhraseMappingInbox(
  page: Page,
  seed: {
    phrase_key: string;
    sample_span: string;
    sample_sentence: string;
    extracted_tag: string;
    last_best_term: string;
  },
): Promise<void> {
  const row = {
    ...seed,
    normalized: seed.phrase_key,
    note_count: 1,
    last_score: 0.62,
    last_best_concept: "",
    last_best_tag: seed.extracted_tag,
    status: "inbox",
    draft_action: "",
    draft_reason: "",
    draft_author: "",
    draft_concept_term: "",
  };
  await page.route("**/api/training/phrase-mappings/ensure", (route) =>
    fulfillJson(route, { ...row }),
  );
  await page.route("**/api/training/phrase-mappings/item**", (route) =>
    fulfillJson(route, { ...row }),
  );
  await page.route("**/api/training/phrase-mappings/draft", (route) => {
    row.status = "draft";
    const body = (route.request().postDataJSON() as { action?: string; reason?: string }) || {};
    row.draft_action = body.action || "exclude";
    row.draft_reason = body.reason || "";
    return fulfillJson(route, { phrase_key: row.phrase_key, status: "draft" });
  });
  await page.route("**/api/training/phrase-mappings/submit", (route) => {
    row.status = "review";
    return fulfillJson(route, { phrase_key: row.phrase_key, status: "review" });
  });
  await page.route("**/api/training/phrase-mappings/send-back", (route) =>
    fulfillJson(route, { phrase_key: row.phrase_key, status: "draft" }),
  );
  await page.route("**/api/training/phrase-mappings/publish", (route) => {
    row.status = "closed";
    return fulfillJson(route, { phrase_key: row.phrase_key, status: "closed" });
  });
}
