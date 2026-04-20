/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
// Four canonical roles. New roles require a design-input change; adding a
// value here without also updating the Neo4j seed is a bug caught by the
// VT-125-TC-004 canonical seed test.
export const CANONICAL_ROLES = [
  "clinician",
  "staff",
  "qa_ra_lead",
  "platform_admin",
] as const;

export type Role = (typeof CANONICAL_ROLES)[number];

export function isRole(value: unknown): value is Role {
  return (
    typeof value === "string" &&
    (CANONICAL_ROLES as readonly string[]).includes(value)
  );
}

export interface NavItem {
  key: string;
  label: string;
  path: string;
  // Icon is intentionally a string key rather than a JSX node so this module
  // stays renderer-agnostic and is trivial to test. The AppShell maps these
  // keys to concrete MUI icons at render time.
  icon?: string;
  activePrefix?: string;
}

export interface RoleNavConfig {
  landing: string;
  primary: NavItem[];
  advanced: NavItem[];
}

export type RoleNavMap = Record<Role, RoleNavConfig>;

// Plain-language copy shown in the RolePicker. Targets Flesch-Kincaid <=9.
export const ROLE_COPY: Record<
  Role,
  { label: string; description: string }
> = {
  clinician: {
    label: "Clinician",
    description:
      "You see patients. LEO opens to the Care Overview so you can find the person you need.",
  },
  staff: {
    label: "Audit or coding staff",
    description:
      "You work through a list of tasks. LEO opens to My Work so your jobs are all in one place.",
  },
  qa_ra_lead: {
    label: "QA or Regulatory lead",
    description:
      "You check how LEO is behaving. LEO opens to Operations so you can see what needs review.",
  },
  platform_admin: {
    label: "Platform admin",
    description:
      "You look after tenants and users. LEO opens to Platform so you can manage them.",
  },
};
