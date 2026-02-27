/**
 * NHS Cancer Waiting Time standards and breach-risk calculation for
 * referral pathways (episodes).
 *
 * Standards modelled:
 *   - 2WW  (14 days): urgent GP referral -> first specialist appointment
 *   - FDS  (28 days): urgent GP referral -> diagnosis / ruling-out
 *   - RTT  (62 days): urgent GP referral -> first definitive treatment
 */

// ── Types ──

export interface Milestone {
  encounter_id: string;
  date: string;
  milestone_type: string;
}

export interface Episode {
  episode_id: string;
  patient_id?: string;
  condition_type: string;
  status: string;
  referral_date?: string;
  milestones?: Milestone[];
  confidence?: number;
  agent_reasoning?: string;
  needs_review?: boolean;
  merged_into?: string;
  merged_from?: string[];
  consolidation_reasoning?: string;
  referral_route?: string;
  place_of_presentation?: string;
  safety_netting_recorded?: boolean;
}

export type RiskLevel = "breached" | "at-risk" | "on-track" | "completed" | "unknown";

export interface BreachTarget {
  label: string;
  standardDays: number;
  startMilestone: string;
  endMilestone: string;
}

export interface BreachStatus {
  target: BreachTarget;
  daysElapsed: number | null;
  daysRemaining: number | null;
  achieved: boolean;
  breached: boolean;
}

export interface PathwayRisk {
  level: RiskLevel;
  worstBreach: BreachStatus | null;
  breaches: BreachStatus[];
  nextExpectedMilestone: string | null;
  sortKey: number;
}

// ── Constants ──

const AT_RISK_THRESHOLD = 0.75;

/** Days after which an unachieved breach is considered "stale" (referral very old). */
export const STALE_DAYS_THRESHOLD = 365;

/** True if episode is likely stale: referral > STALE_DAYS_THRESHOLD ago, no end milestones. */
export function isStaleEpisode(episode: Episode, today: string = todayISO()): boolean {
  const refDate = episode.referral_date;
  if (!refDate) return false;
  const daysSinceReferral = daysBetween(refDate, today);
  if (daysSinceReferral < STALE_DAYS_THRESHOLD) return false;
  const risk = assessPathwayRisk(episode, today);
  const hasAchievedEnd = risk.breaches.some((b) => b.achieved);
  return !hasAchievedEnd;
}

/** Format breach label for display; caps very large overdue counts as "stale". */
export function formatBreachLabel(b: BreachStatus, capStale = true): string {
  if (b.achieved && b.breached) {
    return `${b.target.label}: ${b.daysElapsed}d (breached)`;
  }
  if (b.achieved) {
    return `${b.target.label}: ${b.daysElapsed}d of ${b.target.standardDays}d`;
  }
  const remaining = b.daysRemaining ?? 0;
  const overdue = remaining < 0;
  if (overdue && capStale && Math.abs(remaining) > STALE_DAYS_THRESHOLD) {
    return `${b.target.label}: Likely stale - needs review`;
  }
  if (overdue) {
    return `${b.target.label}: ${Math.abs(remaining)}d overdue`;
  }
  return `${b.target.label}: ${remaining}d left`;
}

export const BREACH_TARGETS: BreachTarget[] = [
  {
    label: "2WW",
    standardDays: 14,
    startMilestone: "referral",
    endMilestone: "first_clinic",
  },
  {
    label: "28-day FDS",
    standardDays: 28,
    startMilestone: "referral",
    endMilestone: "diagnosis",
  },
  {
    label: "62-day RTT",
    standardDays: 62,
    startMilestone: "referral",
    endMilestone: "first_treatment",
  },
];

export const MILESTONE_ORDER = [
  "presentation",
  "referral",
  "first_clinic",
  "diagnosis",
  "treatment_decision",
  "first_treatment",
];

/**
 * Maps raw milestone_type values from the graph/API to canonical names
 * used by breach targets and milestone order.
 * API may return: first_presentation, specialist_visit, first_clinic_visit, etc.
 */
const RAW_TO_CANONICAL: Record<string, string> = {
  first_presentation: "presentation",
  referral_sent: "referral",
  specialist_visit: "first_clinic",
  first_clinic_visit: "first_clinic",
  clinic_visit: "first_clinic",
  diagnosis_confirmed: "diagnosis",
  treatment_started: "first_treatment",
  treatment: "first_treatment",
};

function toCanonicalMilestoneType(raw: string): string {
  return RAW_TO_CANONICAL[raw] ?? raw;
}

/** Normalize milestones: handle API `milestone` key and raw graph values. */
export function normalizeMilestones(
  milestones: Array<{ encounter_id: string; date: string; milestone_type?: string; milestone?: string }> | undefined,
): Milestone[] {
  if (!milestones?.length) return [];
  return milestones
    .filter((m) => m.encounter_id && m.date)
    .map((m) => {
      const raw = m.milestone_type ?? m.milestone ?? "";
      const canonical = toCanonicalMilestoneType(raw);
      return {
        encounter_id: m.encounter_id,
        date: m.date,
        milestone_type: canonical || raw,
      };
    });
}

// ── Helpers ──

export function daysBetween(a: string, b: string): number {
  const msPerDay = 86_400_000;
  return Math.round(
    (new Date(b).getTime() - new Date(a).getTime()) / msPerDay,
  );
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function getMilestoneDate(
  milestones: Milestone[],
  type: string,
): string | null {
  const m = milestones.find((ms) => ms.milestone_type === type);
  return m?.date ?? null;
}

// ── Core logic ──

function evaluateTarget(
  target: BreachTarget,
  milestones: Milestone[],
  referralDate: string | undefined,
  today: string,
): BreachStatus {
  const startDate =
    target.startMilestone === "referral"
      ? (referralDate ?? getMilestoneDate(milestones, "referral"))
      : getMilestoneDate(milestones, target.startMilestone);

  const endDate = getMilestoneDate(milestones, target.endMilestone);

  if (!startDate) {
    return {
      target,
      daysElapsed: null,
      daysRemaining: null,
      achieved: false,
      breached: false,
    };
  }

  if (endDate) {
    const elapsed = daysBetween(startDate, endDate);
    return {
      target,
      daysElapsed: elapsed,
      daysRemaining: target.standardDays - elapsed,
      achieved: true,
      breached: elapsed > target.standardDays,
    };
  }

  const elapsed = daysBetween(startDate, today);
  const remaining = target.standardDays - elapsed;
  return {
    target,
    daysElapsed: elapsed,
    daysRemaining: remaining,
    achieved: false,
    breached: remaining < 0,
  };
}

export function assessPathwayRisk(
  episode: Episode,
  today: string = todayISO(),
): PathwayRisk {
  const milestones = normalizeMilestones(episode.milestones);
  if (episode.status === "completed" || episode.status === "closed") {
    const breaches = BREACH_TARGETS.map((t) =>
      evaluateTarget(t, milestones, episode.referral_date, today),
    );
    const anyBreach = breaches.some((b) => b.breached);
    return {
      level: anyBreach ? "breached" : "completed",
      worstBreach: anyBreach
        ? breaches.filter((b) => b.breached).sort(
            (a, b) => (a.daysRemaining ?? 0) - (b.daysRemaining ?? 0),
          )[0]
        : null,
      breaches,
      nextExpectedMilestone: null,
      sortKey: anyBreach ? 200 : 400,
    };
  }

  if (!episode.referral_date && !getMilestoneDate(milestones, "referral")) {
    return {
      level: "unknown",
      worstBreach: null,
      breaches: [],
      nextExpectedMilestone: nextExpected(milestones),
      sortKey: 300,
    };
  }

  const breaches = BREACH_TARGETS.map((t) =>
    evaluateTarget(t, milestones, episode.referral_date, today),
  );

  const openBreaches = breaches.filter((b) => !b.achieved);
  const anyBreached = openBreaches.some((b) => b.breached);
  const anyAtRisk = openBreaches.some(
    (b) =>
      !b.breached &&
      b.daysRemaining !== null &&
      b.daysElapsed !== null &&
      b.daysElapsed >= b.target.standardDays * AT_RISK_THRESHOLD,
  );

  let level: RiskLevel;
  if (anyBreached) level = "breached";
  else if (anyAtRisk) level = "at-risk";
  else level = "on-track";

  const worst = [...openBreaches]
    .filter((b) => b.daysRemaining !== null)
    .sort((a, b) => (a.daysRemaining ?? 0) - (b.daysRemaining ?? 0))[0] ?? null;

  const sortKey =
    level === "breached"
      ? 0 + (worst?.daysRemaining ?? 0)
      : level === "at-risk"
        ? 100 + (worst?.daysRemaining ?? 99)
        : 300 + (worst?.daysRemaining ?? 99);

  return {
    level,
    worstBreach: worst,
    breaches,
    nextExpectedMilestone: nextExpected(milestones),
    sortKey,
  };
}

function nextExpected(milestones: Milestone[]): string | null {
  const achieved = new Set(milestones.map((m) => m.milestone_type));
  for (const ms of MILESTONE_ORDER) {
    if (!achieved.has(ms)) return ms;
  }
  return null;
}

// ── Aggregate helpers ──

export interface CaseloadSummary {
  total: number;
  onTrack: number;
  atRisk: number;
  breached: number;
  completed: number;
  unknown: number;
}

export function summariseCaseload(
  episodes: Episode[],
  today?: string,
): CaseloadSummary {
  const summary: CaseloadSummary = {
    total: episodes.length,
    onTrack: 0,
    atRisk: 0,
    breached: 0,
    completed: 0,
    unknown: 0,
  };

  for (const ep of episodes) {
    const risk = assessPathwayRisk(ep, today);
    switch (risk.level) {
      case "on-track":
        summary.onTrack++;
        break;
      case "at-risk":
        summary.atRisk++;
        break;
      case "breached":
        summary.breached++;
        break;
      case "completed":
        summary.completed++;
        break;
      default:
        summary.unknown++;
    }
  }
  return summary;
}

export function sortByUrgency(
  episodes: Episode[],
  today?: string,
): Array<Episode & { risk: PathwayRisk }> {
  return episodes
    .map((ep) => ({ ...ep, risk: assessPathwayRisk(ep, today) }))
    .sort((a, b) => a.risk.sortKey - b.risk.sortKey);
}

// ── Patient grouping + convergence detection ──

export type EpisodeWithRisk = Episode & { risk: PathwayRisk };

export interface PatientGroup {
  patientId: string;
  episodes: EpisodeWithRisk[];
  worstRisk: RiskLevel;
  activeCount: number;
  hasConvergenceRisk: boolean;
  convergenceNote: string | null;
  sortKey: number;
}

const RISK_SEVERITY: Record<RiskLevel, number> = {
  breached: 0,
  "at-risk": 1,
  "on-track": 2,
  unknown: 3,
  completed: 4,
};

function worstRiskLevel(episodes: EpisodeWithRisk[]): RiskLevel {
  let worst: RiskLevel = "completed";
  for (const ep of episodes) {
    if (RISK_SEVERITY[ep.risk.level] < RISK_SEVERITY[worst]) {
      worst = ep.risk.level;
    }
  }
  return worst;
}

function detectConvergence(
  episodes: EpisodeWithRisk[],
): { hasRisk: boolean; note: string | null } {
  // Use actual merge metadata from API when available
  const withMergedFrom = episodes.filter(
    (e) => e.merged_from && e.merged_from.length > 0,
  );
  if (withMergedFrom.length > 0) {
    const primary = withMergedFrom[0];
    const mergedCount = primary.merged_from!.length;
    return {
      hasRisk: false,
      note: `${mergedCount} pathway${mergedCount !== 1 ? "s" : ""} consolidated into primary (${primary.consolidation_reasoning || "LLM decision"})`,
    };
  }

  const active = episodes.filter(
    (e) =>
      e.status !== "completed" &&
      e.status !== "closed" &&
      e.status !== "merged",
  );
  if (active.length < 2) {
    return { hasRisk: false, note: null };
  }

  const types = active.map((e) => e.condition_type?.toLowerCase().trim());
  const typeSet = new Set(types.filter(Boolean));

  if (typeSet.size < types.filter(Boolean).length) {
    const duped = types.find(
      (t, i) => t && types.indexOf(t) !== i,
    );
    return {
      hasRisk: true,
      note: `${active.length} active referrals -- possible duplicate for ${duped}`,
    };
  }

  const diagEncounters = active
    .flatMap((e) => e.milestones ?? [])
    .filter((m) => m.milestone_type === "diagnosis")
    .map((m) => m.encounter_id);
  const diagSet = new Set(diagEncounters);
  if (diagEncounters.length > 0 && diagSet.size < diagEncounters.length) {
    return {
      hasRisk: true,
      note: `${active.length} referrals share a diagnosis encounter`,
    };
  }

  return {
    hasRisk: true,
    note: `${active.length} active referrals for this patient`,
  };
}

export function groupByPatient(
  episodes: EpisodeWithRisk[],
): PatientGroup[] {
  const map = new Map<string, EpisodeWithRisk[]>();

  for (const ep of episodes) {
    const key = ep.patient_id ?? `_no_patient_${ep.episode_id}`;
    const list = map.get(key) ?? [];
    list.push(ep);
    map.set(key, list);
  }

  const groups: PatientGroup[] = [];

  for (const [patientId, eps] of map) {
    const sorted = [...eps].sort(
      (a, b) => a.risk.sortKey - b.risk.sortKey,
    );
    const worst = worstRiskLevel(sorted);
    const activeCount = sorted.filter(
      (e) => e.status !== "completed" && e.status !== "closed",
    ).length;
    const convergence = detectConvergence(sorted);

    groups.push({
      patientId,
      episodes: sorted,
      worstRisk: worst,
      activeCount,
      hasConvergenceRisk: convergence.hasRisk,
      convergenceNote: convergence.note,
      sortKey:
        RISK_SEVERITY[worst] * 1000 +
        (convergence.hasRisk ? 0 : 500) +
        (sorted[0]?.risk.sortKey ?? 999),
    });
  }

  return groups.sort((a, b) => a.sortKey - b.sortKey);
}
