/**
 * Playwright stubs for VAL-94AD483A (role and organisation access).
 */

import type { Page } from "@playwright/test";

export const REFERRED_ID = "p-val-referred";
export const DENIED_ID = "p-val-unreferred";
export const DENIED_NHS = "9990000999";
export const HIDDEN_NAME = "Hidden Clinical Name";
export const ACCESS_DENIED = "Access denied";

export type RoleAccessMode = "no_role" | "service_provider" | "icb";

let mode: RoleAccessMode = "no_role";

export function setRoleAccessMode(next: RoleAccessMode): void {
  mode = next;
}

function json(
  route: { fulfill: (r: object) => Promise<void> },
  body: unknown,
  status = 200,
) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function org(scopeType: string) {
  return {
    id: "org-e2e-sp",
    name: "E2E Service Org",
    odsCode: "E2E",
    shortName: "E2E",
    scopeType,
  };
}

function clinicianSession(scopeType: string) {
  return {
    user: { email: "e2e.clinician@example.com", name: "E2E Clinician" },
    isPlatformAdmin: false,
    organizations: [org(scopeType)],
    idleTimeoutMinutes: 30,
    selected_role: "triage_clinician",
    allowed_roles: ["triage_clinician"],
    needs_role_choice: false,
    density_preference: "comfortable",
  };
}

function sessionPayload() {
  if (mode === "no_role") {
    return {
      user: { email: "e2e.norole@example.com", name: "E2E No Role" },
      isPlatformAdmin: false,
      organizations: [org("gp")],
      idleTimeoutMinutes: 30,
      selected_role: null,
      allowed_roles: [],
      needs_role_choice: false,
      density_preference: "comfortable",
    };
  }
  if (mode === "icb") {
    return clinicianSession("icb");
  }
  return clinicianSession("service_provider");
}

function referredSummary() {
  return {
    patient_id: REFERRED_ID,
    nhs_number: "9990000111",
    gender: "female",
    birth_date: "1968-03-12",
    practice_name: "Oak GP",
    episode_count: 1,
    encounter_count: 1,
    last_activity: "2026-08-01",
    active_alert_count: 0,
    document_count: 1,
    referral_count: 1,
    coded_concept_count: 0,
    semantic_tags: [],
    condition_types: ["upper_gi"],
  };
}

function referredDetail() {
  return {
    patient_id: REFERRED_ID,
    display_name: "VAL Referred Patient",
    nhs_number: "9990000111",
    gender: "female",
    birth_date: "1968-03-12",
    practice_name: "Oak GP",
    active_alert_count: 0,
    episodes: [
      {
        episode_id: "ep-val-referred",
        condition_type: "upper_gi",
        status: "active",
        referral_date: "2026-08-01",
      },
    ],
  };
}

function fulfillPatients(
  route: { request: () => { url: () => string }; fulfill: (r: object) => Promise<void> },
) {
  const url = route.request().url();
  if (url.includes("/patients/facets")) {
    return json(route, { condition_types: ["upper_gi"] });
  }
  if (url.includes(DENIED_ID)) {
    return json(route, { detail: ACCESS_DENIED }, 403);
  }
  if (url.includes(REFERRED_ID)) {
    if (
      url.includes("/timeline") ||
      url.includes("/encounters") ||
      url.includes("/documents") ||
      url.includes("/alerts") ||
      url.includes("/coded-entities") ||
      url.includes("/assessments")
    ) {
      return json(route, []);
    }
    return json(route, referredDetail());
  }
  return json(route, {
    total: 1,
    page: 1,
    page_size: 20,
    patients: [referredSummary()],
  });
}

export async function stubRoleAccessValRoutes(page: Page): Promise<void> {
  mode = "no_role";
  await page.route("**/auth/session", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return json(route, sessionPayload());
  });
  await page.route("**/api/proxy/analytics/patients**", (route) =>
    fulfillPatients(route),
  );
}
