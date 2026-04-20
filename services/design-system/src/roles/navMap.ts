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
// Routes match what exists in services/ui/src/app/* today. Phases 2 and 5
// shift some of these paths (e.g. /admin/clinical/* merges into
// /admin/knowledge/*); this map is the source of truth and is updated in
// lockstep with those moves.
export const roleNavMap: RoleNavMap = {
  clinician: {
    landing: "/care/dashboard",
    primary: [
      { key: "care", label: "Care", path: "/care/dashboard", icon: "dashboard" },
      {
        key: "patients",
        label: "Patients",
        path: "/care/patients",
        icon: "people",
        activePrefix: "/care/patients",
      },
      {
        key: "encounters",
        label: "Pathways",
        path: "/care/encounters",
        icon: "timeline",
        activePrefix: "/care/encounters",
      },
      {
        key: "knowledge",
        label: "Knowledge",
        path: "/admin/knowledge",
        icon: "library",
      },
    ],
    advanced: [
      { key: "audit", label: "Audit", path: "/care/audit", icon: "checklist" },
      { key: "reports", label: "Reports", path: "/care/reports", icon: "bar-chart" },
      { key: "portal", label: "Portal", path: "/care/portal", icon: "public" },
    ],
  },
  staff: {
    landing: "/work",
    primary: [
      { key: "work", label: "My work", path: "/work", icon: "inbox" },
      { key: "care", label: "Care", path: "/care/dashboard", icon: "dashboard" },
      {
        key: "knowledge",
        label: "Knowledge",
        path: "/admin/knowledge",
        icon: "library",
      },
    ],
    advanced: [
      { key: "audit", label: "Audit", path: "/care/audit", icon: "checklist" },
      { key: "patients", label: "Patients", path: "/care/patients", icon: "people" },
      { key: "reports", label: "Reports", path: "/care/reports", icon: "bar-chart" },
    ],
  },
  qa_ra_lead: {
    landing: "/admin/operations",
    primary: [
      { key: "operations", label: "Operations", path: "/admin/operations", icon: "monitor" },
      { key: "knowledge", label: "Knowledge", path: "/admin/knowledge", icon: "library" },
      { key: "care", label: "Care", path: "/care/dashboard", icon: "dashboard" },
    ],
    advanced: [
      { key: "platform", label: "Platform", path: "/admin/platform", icon: "build" },
      { key: "users", label: "Users", path: "/admin/users", icon: "people" },
      { key: "audit", label: "Audit", path: "/care/audit", icon: "checklist" },
    ],
  },
  platform_admin: {
    landing: "/admin/platform",
    primary: [
      { key: "platform", label: "Platform", path: "/admin/platform", icon: "build" },
      { key: "users", label: "Users", path: "/admin/users", icon: "people" },
      { key: "knowledge", label: "Knowledge", path: "/admin/knowledge", icon: "library" },
      { key: "operations", label: "Operations", path: "/admin/operations", icon: "monitor" },
    ],
    advanced: [
      { key: "care", label: "Care", path: "/care/dashboard", icon: "dashboard" },
      { key: "audit", label: "Audit", path: "/care/audit", icon: "checklist" },
      { key: "reports", label: "Reports", path: "/care/reports", icon: "bar-chart" },
    ],
  },
};

export function landingForRole(role: Role): string {
  return roleNavMap[role].landing;
}
