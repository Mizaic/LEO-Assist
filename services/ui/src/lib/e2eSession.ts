export const E2E_SESSION_PAYLOAD = {
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
  idleTimeoutMinutes: 30,
  selected_role: "platform_admin",
  allowed_roles: ["platform_admin", "triage_clinician", "auditor"],
  needs_role_choice: false,
  density_preference: "comfortable",
};

// IMPORTANT: NEXT_PUBLIC_E2E_MODE must NOT appear in any deployed .env file.
// It activates a platform-admin bypass and is only safe in local development.
export function isE2eAuthMode(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_E2E_MODE === "true"
  );
}

export function assertE2eModeNotInProduction(): void {
  if (
    process.env.NEXT_PUBLIC_E2E_MODE === "true" &&
    process.env.NODE_ENV === "production"
  ) {
    throw new Error(
      "SECURITY: NEXT_PUBLIC_E2E_MODE must never be set in a production build. " +
        "Remove it from all deployed environment configurations.",
    );
  }
}
