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
  // -- Clinical Roles -------------------------------------------------------
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
  clinical_coder: {
    landing: "/work",
    primary: [_WORK, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_AUDIT, _CARE_PATIENTS, _REPORTS],
  },
  auditor: {
    landing: "/care/audit",
    primary: [_AUDIT, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_OPERATIONS, _CARE_PATIENTS, _REPORTS],
  },
  // -- Administration & Management ------------------------------------------
  appointment_booking: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_REPORTS, _PORTAL],
  },
  clinical_administrator: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _CARE_PATIENTS, _OPERATIONS, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS, _PORTAL],
  },
  referral_supervisor: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_ENCOUNTERS, _CARE_DASHBOARD],
    advanced: [_AUDIT, _REPORTS],
  },
  registration_administrator: {
    landing: "/care/patients",
    primary: [_CARE_PATIENTS, _CARE_DASHBOARD],
    advanced: [_USERS, _REPORTS],
  },
  // -- System & Onboarding --------------------------------------------------
  pathway_supervisor: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _CARE_PATIENTS, _CARE_ENCOUNTERS, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS, _PORTAL],
  },
  org_admin: {
    landing: "/admin/portal",
    primary: [_ADMIN_PORTAL, _USERS, _CARE_DASHBOARD],
    advanced: [_AUDIT, _REPORTS, _KNOWLEDGE],
  },
  pipeline_operator: {
    landing: "/admin/operations",
    primary: [_OPERATIONS, _CARE_DASHBOARD, _KNOWLEDGE],
    advanced: [_AUDIT, _REPORTS],
  },
  platform_admin: {
    landing: "/admin/platform",
    primary: [_PLATFORM, _USERS, _KNOWLEDGE, _OPERATIONS],
    advanced: [_CARE_DASHBOARD, _AUDIT, _REPORTS],
  },
  // -- Other / Viewer -------------------------------------------------------
  clinical_viewer: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _CARE_PATIENTS, _REPORTS],
    advanced: [_AUDIT, _PORTAL],
  },
  read_only: {
    landing: "/care/dashboard",
    primary: [_CARE_DASHBOARD, _REPORTS],
    advanced: [_PORTAL],
  },
};

export function landingForRole(role: Role): string {
  return roleNavMap[role].landing;
}
