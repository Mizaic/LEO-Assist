/**
 * Playwright stubs for VAL-469227B6 (unified patient record).
 */

import type { Page } from "@playwright/test";

export const MIXED_ID = "p-val-mixed";
export const PRIMARY_ID = "p-val-primary";
export const MIXED_NAME = "VAL Mixed Episodes";
export const PRIMARY_NAME = "VAL Primary Care";

const CANCER_EPISODE = "breast";
const REFERRAL_EPISODE = "referral";
const PRIMARY_EPISODE = "primary care";

export const TIMELINE_LABELS = {
  encounter: "GP review",
  episode: "Primary care episode",
  alert: "Safety alert",
  document: "Clinic letter",
} as const;

function json(
  route: { fulfill: (r: object) => Promise<void> },
  body: unknown,
) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function summary(
  patientId: string,
  conditionTypes: string[],
  extras: { referral_count?: number },
) {
  return {
    patient_id: patientId,
    nhs_number: patientId === MIXED_ID ? "9990000101" : "9990000102",
    gender: "female",
    birth_date: "1965-04-12",
    practice_name: "Oak GP",
    episode_count: conditionTypes.length,
    encounter_count: 1,
    last_activity: "2026-08-20",
    active_alert_count: 0,
    document_count: 1,
    referral_count: extras.referral_count ?? 0,
    coded_concept_count: 0,
    semantic_tags: [],
    condition_types: conditionTypes,
  };
}

function episode(
  episodeId: string,
  conditionType: string,
  extras: Record<string, unknown> = {},
) {
  return {
    episode_id: episodeId,
    condition_type: conditionType,
    status: "active",
    referral_date: extras.referral_date ?? null,
    end_date: null,
    first_presentation_date: null,
    inferred_outcome: extras.inferred_outcome ?? null,
    staging_value: extras.staging_value ?? null,
    staging_early_late: extras.staging_early_late ?? null,
    referral_route: null,
    place_of_presentation: null,
    prior_consultations_n: null,
    safety_netting_recorded: null,
  };
}

function mixedDetail() {
  return {
    patient_id: MIXED_ID,
    display_name: MIXED_NAME,
    nhs_number: "9990000101",
    gender: "female",
    birth_date: "1965-04-12",
    practice_name: "Oak GP",
    active_alert_count: 0,
    episodes: [
      episode("ep-breast", CANCER_EPISODE, {
        inferred_outcome: "cancer",
        staging_value: "I",
        referral_date: "2026-01-10",
      }),
      episode("ep-referral", REFERRAL_EPISODE, {
        referral_date: "2026-06-01",
      }),
      episode("ep-primary", PRIMARY_EPISODE),
    ],
  };
}

function primaryDetail() {
  return {
    patient_id: PRIMARY_ID,
    display_name: PRIMARY_NAME,
    nhs_number: "9990000102",
    gender: "male",
    birth_date: "1972-09-03",
    practice_name: "Oak GP",
    active_alert_count: 1,
    episodes: [episode("ep-pc-1", PRIMARY_EPISODE)],
  };
}

function primaryTimeline() {
  return [
    {
      item_type: "encounter",
      item_id: "enc-1",
      item_date: "2026-08-20",
      label: TIMELINE_LABELS.encounter,
      extra: null,
    },
    {
      item_type: "episode",
      item_id: "ep-pc-1",
      item_date: "2026-08-15",
      label: TIMELINE_LABELS.episode,
      extra: null,
    },
    {
      item_type: "alert",
      item_id: "alert-1",
      item_date: "2026-08-10",
      label: TIMELINE_LABELS.alert,
      extra: null,
    },
    {
      item_type: "document",
      item_id: "doc-1",
      item_date: "2026-08-01",
      label: TIMELINE_LABELS.document,
      extra: null,
    },
  ];
}

function listResponse() {
  return {
    total: 2,
    page: 1,
    page_size: 20,
    patients: [
      summary(MIXED_ID, [CANCER_EPISODE, REFERRAL_EPISODE, PRIMARY_EPISODE], {
        referral_count: 1,
      }),
      summary(PRIMARY_ID, [PRIMARY_EPISODE], {}),
    ],
  };
}

function patientIdFromPath(pathname: string): string | null {
  const match = pathname.match(/\/patients\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export async function stubUnifiedPatientRecordValRoutes(
  page: Page,
): Promise<void> {
  await page.route("**/api/proxy/analytics/patients/*/timeline", (route) => {
    const path = new URL(route.request().url()).pathname;
    const patientId = patientIdFromPath(path);
    return json(route, patientId === PRIMARY_ID ? primaryTimeline() : []);
  });
  await page.route("**/api/proxy/analytics/patients**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/facets")) {
      return json(route, {
        condition_types: [CANCER_EPISODE, REFERRAL_EPISODE, PRIMARY_EPISODE],
      });
    }
    if (path.includes("/timeline")) {
      const patientId = patientIdFromPath(path);
      return json(route, patientId === PRIMARY_ID ? primaryTimeline() : []);
    }
    const patientId = patientIdFromPath(path);
    if (!patientId) {
      return json(route, listResponse());
    }
    if (path.includes("/milestones")) {
      return json(route, { steps: [] });
    }
    if (path.includes("/coded-entities")) {
      return json(route, []);
    }
    if (path.includes("/assessments")) {
      return json(route, []);
    }
    if (path.includes("/alerts")) {
      return json(route, []);
    }
    if (path.includes("/encounters")) {
      return json(route, []);
    }
    if (path.includes("/documents")) {
      return json(route, []);
    }
    if (patientId === MIXED_ID) {
      return json(route, mixedDetail());
    }
    if (patientId === PRIMARY_ID) {
      return json(route, primaryDetail());
    }
    return json(route, { detail: "not found" });
  });
}
