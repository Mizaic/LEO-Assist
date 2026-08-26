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
// 28 canonical roles aligned to the HCCP platform role catalog.
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
  "appointment_manual_booking",
  "advice_and_guidance",
  "create_referral",
  "clinician_admin",
  "referring_clinician",
  "receptionist",
  "reporting_sonographer",
  "sonographer_qa",
  "validation",
  // Operations & management
  "pathway_supervisor",
  "referral_supervisor",
  "operations_manager",
  // Support & compliance
  "support_agent",
  "support_supervisor",
  "regulatory_reviewer",
  // LMS
  "lms_admin",
  "lms_manager",
  "lms_learner",
  "lms_training_manager",
  // Onboarding
  "customer_onboarding",
  "technical_onboarding",
  // Admin
  "administrator",
  "organization_administrator",
  // EDMS
  "point_of_care_clinician",
  "medical_records_viewer",
  // Registration
  "registration_admin",
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
  | "Clinical"
  | "Operations & Management"
  | "Support & Compliance"
  | "LMS"
  | "Onboarding"
  | "Admin"
  | "EDMS"
  | "Registration";

export interface RoleCopyEntry {
  label: string;
  description: string;
  category: RoleCategory;
  // ASCII icon key mapped to a concrete MUI icon by the AppShell.
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
  // -- Clinical -------------------------------------------------------------
  triage_clinician: {
    label: "Triage Clinician",
    description: "Assess and prioritise patient referrals for the pathway.",
    category: "Clinical",
    icon: "stethoscope",
  },
  admin_triage: {
    label: "Admin Triage",
    description: "Provide administrative support during patient triage.",
    category: "Clinical",
    icon: "local-hospital",
  },
  appointment_manual_booking: {
    label: "Appointment Booking",
    description: "Manually book and manage patient appointments.",
    category: "Clinical",
    icon: "calendar-today",
  },
  advice_and_guidance: {
    label: "Advice & Guidance",
    description: "Handle Advice and Guidance requests from referring clinicians.",
    category: "Clinical",
    icon: "chat",
  },
  create_referral: {
    label: "Create Referral",
    description: "Create and submit patient referrals.",
    category: "Clinical",
    icon: "send",
  },
  clinician_admin: {
    label: "Clinical Administrator",
    description: "Oversee clinical administration and pathway management.",
    category: "Clinical",
    icon: "assignment",
  },
  referring_clinician: {
    label: "Referring Clinician",
    description: "Create and manage referrals for patients.",
    category: "Clinical",
    icon: "person-add",
  },
  receptionist: {
    label: "Receptionist",
    description: "Manage reception and patient appointment bookings.",
    category: "Clinical",
    icon: "desk",
  },
  reporting_sonographer: {
    label: "Reporting Sonographer",
    description: "Review imaging and produce diagnostic reports.",
    category: "Clinical",
    icon: "biotech",
  },
  sonographer_qa: {
    label: "Sonographer QA",
    description: "Quality assurance for imaging studies.",
    category: "Clinical",
    icon: "verified",
  },
  validation: {
    label: "Validation",
    description: "Validate and verify clinical data.",
    category: "Clinical",
    icon: "fact-check",
  },
  // -- Operations & Management ----------------------------------------------
  pathway_supervisor: {
    label: "Pathway Supervisor",
    description: "Monitor and manage patient pathways across the service.",
    category: "Operations & Management",
    icon: "route",
  },
  referral_supervisor: {
    label: "Referral Supervisor",
    description: "Oversee referral processing and manage workflow queues.",
    category: "Operations & Management",
    icon: "swap-horiz",
  },
  operations_manager: {
    label: "Operations Manager",
    description: "Operational oversight, analytics, and reporting.",
    category: "Operations & Management",
    icon: "bar-chart",
  },
  // -- Support & Compliance -------------------------------------------------
  support_agent: {
    label: "Support Agent",
    description: "Handle first-line support tickets.",
    category: "Support & Compliance",
    icon: "headset-mic",
  },
  support_supervisor: {
    label: "Support Supervisor",
    description: "Supervise the support team and review all tickets.",
    category: "Support & Compliance",
    icon: "supervisor-account",
  },
  regulatory_reviewer: {
    label: "Regulatory Reviewer",
    description: "Access records for regulatory compliance and audit.",
    category: "Support & Compliance",
    icon: "gavel",
  },
  // -- LMS ------------------------------------------------------------------
  lms_admin: {
    label: "LMS Administrator",
    description: "Author, approve, and manage all training content.",
    category: "LMS",
    icon: "school",
  },
  lms_manager: {
    label: "LMS Training Manager",
    description: "Oversee team training enrolments and progress.",
    category: "LMS",
    icon: "manage-accounts",
  },
  lms_learner: {
    label: "LMS Learner",
    description: "Access and complete training programmes.",
    category: "LMS",
    icon: "menu-book",
  },
  lms_training_manager: {
    label: "LMS Training Manager (legacy)",
    description: "Deprecated -- use lms_manager.",
    category: "LMS",
    icon: "manage-accounts",
  },
  // -- Onboarding -----------------------------------------------------------
  customer_onboarding: {
    label: "Customer Onboarding",
    description: "Onboard new customers and manage their users.",
    category: "Onboarding",
    icon: "domain-add",
  },
  technical_onboarding: {
    label: "Technical Onboarding",
    description: "Set up and validate technical system access.",
    category: "Onboarding",
    icon: "settings-suggest",
  },
  // -- Admin ----------------------------------------------------------------
  administrator: {
    label: "System Administrator",
    description: "Full platform access -- manage tenants, users, and settings.",
    category: "Admin",
    icon: "admin-panel-settings",
  },
  organization_administrator: {
    label: "Organisation Administrator",
    description: "Manage users, groups, and settings within your organisation.",
    category: "Admin",
    icon: "business",
  },
  // -- EDMS -----------------------------------------------------------------
  point_of_care_clinician: {
    label: "Point of Care Clinician",
    description: "View patient documents at the point of care.",
    category: "EDMS",
    icon: "local-hospital",
  },
  medical_records_viewer: {
    label: "Medical Records Viewer",
    description: "Reactive access to patient medical records.",
    category: "EDMS",
    icon: "folder-shared",
  },
  // -- Registration ---------------------------------------------------------
  registration_admin: {
    label: "Registration Admin",
    description: "Manage patient registration and data quality.",
    category: "Registration",
    icon: "how-to-reg",
  },
};
