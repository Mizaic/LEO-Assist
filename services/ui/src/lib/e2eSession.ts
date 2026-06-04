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
  allowed_roles: ["platform_admin", "clinician", "qa_ra_lead"],
  needs_role_choice: false,
  density_preference: "comfortable",
};

export function isE2eAuthMode(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_E2E_MODE === "true"
  );
}
