/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */

// -- Role catalog -----------------------------------------------------------
//
// 14 canonical roles spanning clinical, admin, system, and viewer surfaces.
// Adding a role requires:
//   1. A new entry in CANONICAL_ROLES (here)
//   2. An entry in ROLE_COPY (label, description, category, icon)
//   3. An entry in navMap.ts (landing, primary nav, advanced nav)
//   4. An entry in libs/cypher/role_queries.py CANONICAL_ROLES
//   5. An entry in tenant_seed.py DEFAULT_ROLES (permissions + description)
//   6. Neo4j seed run: scripts/seed_roles_and_groups.py

export const CANONICAL_ROLES = [
  // Clinical
  "triage_clinician",
  "admin_triage",
  "clinical_coder",
  "auditor",
  // Administration & management
  "appointment_booking",
  "clinical_administrator",
  "referral_supervisor",
  "registration_administrator",
  // System & onboarding
  "pathway_supervisor",
  "org_admin",
  "pipeline_operator",
  "platform_admin",
  // Other / viewer
  "clinical_viewer",
  "read_only",
] as const;

export type Role = (typeof CANONICAL_ROLES)[number];

export function isRole(value: unknown): value is Role {
  return (
    typeof value === "string" &&
    (CANONICAL_ROLES as readonly string[]).includes(value)
  );
}

// -- Navigation types -------------------------------------------------------

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

// -- Picker display types ---------------------------------------------------

// Categories used to group roles in the picker UI.
export type RoleCategory =
  | "Clinical Roles"
  | "Administration & Management"
  | "System & Onboarding"
  | "Other";

export interface RoleCopyEntry {
  label: string;
  description: string;
  category: RoleCategory;
  // Emoji icon displayed on the picker card.
  icon: string;
}

// Org option passed to RolePicker for the org-selection step.
export interface OrgOption {
  id: string;
  name: string;
  odsCode?: string;
  shortName?: string;
  scopeType?: string;
}

// -- Role copy (plain English, Flesch-Kincaid <=9) -------------------------

export const ROLE_COPY: Record<Role, RoleCopyEntry> = {
  // -- Clinical Roles -------------------------------------------------------
  triage_clinician: {
    label: "Triage Clinician",
    description: "Assess and prioritise patient referrals for the pathway.",
    category: "Clinical Roles",
    icon: "🩺",
  },
  admin_triage: {
    label: "Admin Triage",
    description: "Provide administrative support during patient triage.",
    category: "Clinical Roles",
    icon: "🏥",
  },
  clinical_coder: {
    label: "Clinical Coder",
    description: "Code clinical encounters from patient notes.",
    category: "Clinical Roles",
    icon: "🏷️",
  },
  auditor: {
    label: "Auditor",
    description: "Review coding quality and perform clinical audits.",
    category: "Clinical Roles",
    icon: "✅",
  },
  // -- Administration & Management ------------------------------------------
  appointment_booking: {
    label: "Appointment Booking",
    description: "Manually book and manage patient appointments.",
    category: "Administration & Management",
    icon: "📅",
  },
  clinical_administrator: {
    label: "Clinical Administrator",
    description: "Oversee clinical administration and day-to-day operations.",
    category: "Administration & Management",
    icon: "📋",
  },
  referral_supervisor: {
    label: "Referral Supervisor",
    description: "Oversee referral processing and manage workflow queues.",
    category: "Administration & Management",
    icon: "🔄",
  },
  registration_administrator: {
    label: "Registration Administrator",
    description: "Manage patient registration and data quality.",
    category: "Administration & Management",
    icon: "👤",
  },
  // -- System & Onboarding --------------------------------------------------
  pathway_supervisor: {
    label: "Pathway Supervisor",
    description: "Monitor and manage patient pathways across the service.",
    category: "System & Onboarding",
    icon: "👥",
  },
  org_admin: {
    label: "Organisation Admin",
    description: "Manage users, groups, and sub-organisations in your org.",
    category: "System & Onboarding",
    icon: "🏢",
  },
  pipeline_operator: {
    label: "Pipeline Operator",
    description: "Run and monitor the AI coding pipeline.",
    category: "System & Onboarding",
    icon: "⚡",
  },
  platform_admin: {
    label: "Platform Admin",
    description: "Full platform access — manage tenants, users, and settings.",
    category: "System & Onboarding",
    icon: "⚙️",
  },
  // -- Other / Viewer -------------------------------------------------------
  clinical_viewer: {
    label: "Clinical Viewer",
    description: "Read-only access to patient data and reports.",
    category: "Other",
    icon: "👁️",
  },
  read_only: {
    label: "Read Only",
    description: "Basic read-only access to the platform.",
    category: "Other",
    icon: "🔒",
  },
};
