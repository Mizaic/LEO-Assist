/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A59215DA
 *   DI: DI-900CB621
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A59215DA")
 */
import type { IntroRoleCopy } from "@leo/design-system";

// AREA_INTRO_COPY -- role-aware intro copy for every major landing
// page. See DI-LEO-AI-139 and VT-LEO-AI-135.
//
// Readability rule: every `default` block MUST grade at Flesch-Kincaid 9
// or below. Role-specific blocks may go to grade 12 for power-user
// terminology where the role is a specialist. The test at
// __tests__/area-copy-readability.test.ts pins the rule.

export type AreaKey =
  | "care-overview"
  | "operations"
  | "pathway-explorer"
  | "platform"
  | "users"
  | "portal"
  | "support"
  | "settings"
  | "work";

export const AREA_INTRO_COPY: Record<AreaKey, IntroRoleCopy> = {
  "care-overview": {
    default: {
      title: "Care Overview",
      lede: "Your main view of patients and team work today.",
      how: "Pick a tile to see the list behind the number.",
      what: "Each tile links to the page that acts on that list.",
    },
    triage_clinician: {
      title: "Care Overview",
      lede: "Your active patients and the tasks linked to them.",
      how: "Open a tile to see the patients behind it.",
      what: "Click a patient to open the full record.",
    },
    clinical_coder: {
      title: "Care Overview",
      lede: "Today's open work for your team in one view.",
      how: "Open the red tiles first. They are the most urgent.",
      what: "Each row links to the screen that clears the task.",
    },
    auditor: {
      title: "Care Overview",
      lede: "How the team is coping today, with throughput and safety trends.",
      how: "Open any tile to see the drill down and source filters.",
      what: "Follow the drill down for an audit-ready evidence trail.",
    },
  },
  operations: {
    default: {
      title: "Operations Console",
      lede: "Run coding jobs, watch progress, and check results.",
      how: "Start a new run or reopen a recent one.",
      what: "Each run produces codes for the team to review.",
    },
    platform_admin: {
      title: "Operations Console",
      lede: "Run coding jobs, watch progress, and check results.",
      how: "Start a run, check the job list, or drill into a batch.",
      what: "Outputs flow to the coding review and audit queues.",
    },
    clinical_coder: {
      title: "Operations Console",
      lede: "Kick off coding runs and pick up review work as it lands.",
      how: "Start a run, then open the review queue when it finishes.",
      what: "Each finished run adds rows to your work queue.",
    },
    auditor: {
      title: "Operations Console",
      lede: "Oversight of every coding run, with QA drill-downs by site.",
      how: "Filter by site or pathway to focus a review window.",
      what: "All runs carry an audit log that you can export.",
    },
  },
  "pathway-explorer": {
    default: {
      title: "Pathway Explorer",
      lede: "See how patients move through a care pathway.",
      how: "Pick a pathway to see the steps and who is at each one.",
      what: "Click a step to see the patients parked there.",
    },
    triage_clinician: {
      title: "Pathway Explorer",
      lede: "Where your patients sit on each care pathway.",
      how: "Open a pathway to see which step each patient is at.",
      what: "Click a step to open the patients waiting at it.",
    },
    auditor: {
      title: "Pathway Explorer",
      lede: "Pathway step counts, wait times, and outlier detection.",
      how: "Use the filters to focus on a site or a cohort.",
      what: "Drill into a step for its evidence bundle and audit trail.",
    },
  },
  platform: {
    default: {
      title: "Platform",
      lede: "System health, costs, and the settings for your site.",
      how: "Open a card to change a setting or see a trend.",
      what: "Changes take effect on the next pipeline run.",
    },
    platform_admin: {
      title: "Platform",
      lede: "System health, costs, and settings for this deployment.",
      how: "Drill in for per-service metrics, quotas, and audit logs.",
      what: "Most changes take effect within one pipeline cycle.",
    },
  },
  users: {
    default: {
      title: "Users",
      lede: "People who use LEO at your site, with roles and access.",
      how: "Pick a person to change their role or access.",
      what: "Every change is logged for audit.",
    },
    platform_admin: {
      title: "Users",
      lede: "Manage practitioners, roles, and org access for this site.",
      how: "Open a user to change their role or remove access.",
      what: "Every change writes an append-only audit entry.",
    },
    auditor: {
      title: "Users",
      lede: "Who has access, what role they hold, and when they last signed in.",
      how: "Filter by role or org to prepare an access review.",
      what: "Role changes appear in the audit log within seconds.",
    },
  },
  portal: {
    default: {
      title: "Patient Portal",
      lede: "What your patients see when they log in.",
      how: "Pick a section to see or change what patients get.",
      what: "Changes go live the next time a patient opens the app.",
    },
    triage_clinician: {
      title: "Patient Portal",
      lede: "What your patients see when they log in.",
      how: "Pick a section to review or change the patient view.",
      what: "Patient messages land in your inbox for review.",
    },
    platform_admin: {
      title: "Patient Portal",
      lede: "Public-facing portal settings for your organisation.",
      how: "Open the content or access tabs to change what patients see.",
      what: "Every change writes to the audit log.",
    },
  },
  support: {
    default: {
      title: "Support",
      lede: "Get help, read guides, or raise a ticket.",
      how: "Pick a guide or start a new ticket.",
      what: "Our team replies to tickets the same working day.",
    },
  },
  settings: {
    default: {
      title: "Settings",
      lede: "Your personal settings for LEO.",
      how: "Pick the thing you want to change.",
      what: "Changes save as soon as you make them.",
    },
  },
  work: {
    default: {
      title: "My Work",
      lede: "Every open task for you, in one place.",
      how: "Start at the top. The red rows go first.",
      what: "Each link opens the screen that clears the task.",
    },
    clinical_coder: {
      title: "My Work",
      lede: "Every open task for you, in one place.",
      how: "Start at the top. The red rows go first.",
      what: "Each link opens the page that clears the task.",
    },
    auditor: {
      title: "Team Work",
      lede: "Tasks your team has open across code, safety, and labels.",
      how: "Filter by source to see one queue at a time.",
      what: "Each link opens the screen used to resolve the item.",
    },
  },
};
