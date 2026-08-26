/**
 * Playwright stubs for VAL-8D24CBE6 (stay signed in while working).
 */

import type { Page } from "@playwright/test";

export const IDLE_MINUTES_ON = 1;
export const IDLE_OFF_COPY =
  "Set to 0 to turn idle expiry off";
export const IDLE_WARN_COPY =
  "If someone does not use the app for this long, warn them and end the server session.";

export const patchedBodies: Record<string, unknown>[] = [];

let idleTimeoutMinutes = 30;

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function authConfig() {
  return {
    session_ttl_hours: 168,
    idle_timeout_minutes: idleTimeoutMinutes,
    cookie_secure: false,
    require_mfa: false,
  };
}

function sessions() {
  return [
    {
      session_id: "sess-val-keepalive",
      email: "e2e.clinician@example.com",
      ttl_seconds: 3600,
    },
  ];
}

export async function stubSessionKeepaliveValRoutes(page: Page): Promise<void> {
  patchedBodies.length = 0;
  idleTimeoutMinutes = 30;

  await page.route("**/auth/session", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return json(route, {
      user: {
        email: "e2e.clinician@example.com",
        name: "E2E Clinician",
      },
      isPlatformAdmin: true,
      organizations: [
        {
          id: "org-e2e",
          name: "E2E Test Organisation",
          odsCode: "E2E",
          shortName: "E2E",
          type: "test",
        },
      ],
      idleTimeoutMinutes: IDLE_MINUTES_ON,
      selected_role: "administrator",
      allowed_roles: ["administrator", "triage_clinician", "regulatory_reviewer"],
      needs_role_choice: false,
      density_preference: "comfortable",
    });
  });

  await page.route("**/api/admin/auth-config**", (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      patchedBodies.push(body);
      if (typeof body.idle_timeout_minutes === "number") {
        idleTimeoutMinutes = body.idle_timeout_minutes;
      }
      return json(route, {
        session_ttl_hours: authConfig().session_ttl_hours,
        idle_timeout_minutes: idleTimeoutMinutes,
      });
    }
    return json(route, authConfig());
  });

  await page.route("**/api/admin/sessions**", (route) => json(route, sessions()));
}
