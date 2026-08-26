/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-10218528
 *   DI: DI-FAF97A8C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-10218528")
 */
import type { Role, RoleNavMap } from "./types";

// Role-scoped nav. Items not in `primary` are collected into `advanced`
// and surfaced behind the "Advanced" tray in AppShell.
//
// Routes match what exists in services/ui/src/app/* today.

const _CARE_PATIENTS = { key: "patients", label: "Patients", path: "/care/patients", icon: "people", activePrefix: "/care/patients" };
const _CARE_DASHBOARD = { key: "care", label: "Care", path: "/care/dashboard", icon: "dashboard" };
const _CARE_ENCOUNTERS = { key: "encounters", label: "Pathways", path: "/care/encounters", icon: "timeline", activePrefix: "/care/encounters" };
const _KNOWLEDGE = { key: "knowledge", label: "Knowledge", path: "/admin/knowledge", icon: "library" };
const _WORK = { key: "work", label: "My work", path: "/work", icon: "inbox" };
const _OPERATIONS = { key: "operations", label: "Operations", path: "/admin/operations", icon: "monitor" };
const _PLATFORM = { key: "platform", label: "Platform", path: "/admin/platform", icon: "build" };
const _USERS = { key: "users", label: "Users", path: "/admin/users", icon: "people" };
const _AUDIT = { key: "audit", label: "Audit", path: "/care/audit", icon: "checklist" };
const _REPORTS = { key: "reports", label: "Reports", path: "/care/reports", icon: "bar-chart" };
const _PORTAL = { key: "portal", label: "Portal", path: "/care/portal", icon: "public" };
const _ADMIN_PORTAL = { key: "admin-portal", label: "Admin", path: "/admin/portal", icon: "settings" };

export const roleNavMap: RoleNavMap = {
  // -- Clinical -------------------------------------------------------------
  triage_clinician: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _CARE_ENCOUNTERS, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS, _PORTAL],
  },
  admin_triage: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_REPORTS, _PORTAL],
  },
  appointment_manual_booking: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_REPORTS, _PORTAL],
  },
  advice_and_guidance: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS],
  },
  create_referral: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_REPORTS, _PORTAL],
  },
  clinician_admin: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _CARE_PATIENTS, _OPERATIONS, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS, _PORTAL],
  },
  referring_clinician: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_REPORTS, _PORTAL],
  },
  receptionist: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_REPORTS, _PORTAL],
  },
  reporting_sonographer: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_REPORTS],
  },
  sonographer_qa: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS],
  },
  validation: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS],
  },
  // -- Operations & Management ----------------------------------------------
  pathway_supervisor: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _CARE_PATIENTS, _CARE_ENCOUNTERS, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS, _PORTAL],
  },
  referral_supervisor: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_ENCOUNTERS, _CARE_DASHBOARD],
    advanced: [_AUDIT, _REPORTS],
  },
  operations_manager: {
    landing: "/admin/operations",
    primary: [_OPERATIONS, _CARE_DASHBOARD, _REPORTS],
    advanced: [_AUDIT, _KNOWLEDGE, _USERS],
  },
  // -- Support & Compliance -------------------------------------------------
  support_agent: {
    landing: "/admin/operations",
    primary: [_OPERATIONS, _CARE_DASHBOARD],
    advanced: [_REPORTS],
  },
  support_supervisor: {
    landing: "/admin/operations",
    primary: [_OPERATIONS, _CARE_DASHBOARD, _USERS],
    advanced: [_AUDIT, _REPORTS],
  },
  regulatory_reviewer: {
    landing: "/care/audit",
    primary: [_AUDIT, _CARE_PATIENTS, _REPORTS],
    advanced: [_OPERATIONS],
  },
  // -- LMS ------------------------------------------------------------------
  lms_admin: {
    landing: "/admin/knowledge",
    primary: [_KNOWLEDGE, _USERS, _OPERATIONS],
    advanced: [_AUDIT, _REPORTS],
  },
  lms_manager: {
    landing: "/admin/knowledge",
    primary: [_KNOWLEDGE, _USERS],
    advanced: [_REPORTS],
  },
  lms_learner: {
    landing: "/admin/knowledge",
    primary: [_KNOWLEDGE],
    advanced: [_PORTAL],
  },
  lms_training_manager: {
    landing: "/admin/knowledge",
    primary: [_KNOWLEDGE, _USERS],
    advanced: [_REPORTS],
  },
  // -- Onboarding -----------------------------------------------------------
  customer_onboarding: {
    landing: "/admin/portal",
    primary: [_ADMIN_PORTAL, _USERS, _KNOWLEDGE],
    advanced: [_REPORTS],
  },
  technical_onboarding: {
    landing: "/admin/portal",
    primary: [_ADMIN_PORTAL, _OPERATIONS],
    advanced: [_KNOWLEDGE, _REPORTS],
  },
  // -- Admin ----------------------------------------------------------------
  administrator: {
    landing: "/admin/knowledge",
    primary: [_PLATFORM, _USERS, _KNOWLEDGE, _OPERATIONS],
    advanced: [_CARE_DASHBOARD, _AUDIT, _REPORTS],
  },
  organization_administrator: {
    landing: "/admin/portal",
    primary: [_ADMIN_PORTAL, _USERS, _CARE_DASHBOARD],
    advanced: [_AUDIT, _REPORTS, _KNOWLEDGE],
  },
  // -- EDMS -----------------------------------------------------------------
  point_of_care_clinician: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_PORTAL],
  },
  medical_records_viewer: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_AUDIT, _PORTAL],
  },
  // -- Registration ---------------------------------------------------------
  registration_admin: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_USERS, _REPORTS],
  },
};

export function landingForRole(role: Role): string {
  return roleNavMap[role].landing;
}
