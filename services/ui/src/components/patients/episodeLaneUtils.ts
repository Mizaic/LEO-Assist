/**
 * Shared helpers for EPR episode swimlane cards.
 *
 * Atlas: DI-357A7468 / DO-5D3EA371
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
import type { EpisodeSummaryEpr, TimelineItem } from "@/lib/patientEprApi";

export const DAY_MS = 24 * 60 * 60 * 1000;

export const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  lower_gi: "#B45309",
  upper_gi: "#7C3AED",
  skin: "#047857",
  haematology: "#0369A1",
  gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8",
  urology: "#4338CA",
};

export const MILESTONE_LABEL: Record<string, string> = {
  referral: "GP Referral",
  specialist_visit: "First specialist",
  diagnosis: "Diagnosis",
  outcome: "Outcome",
};

export function accentFor(t: string | null): string {
  const key = (t ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

export function dateToTs(iso: string | null | undefined): number {
  if (!iso) return 0;
  try {
    return new Date(iso).getTime();
  } catch {
    return 0;
  }
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export function daysBetween(
  a: string | null | undefined,
  b: string | null | undefined,
): number | null {
  const ta = dateToTs(a);
  const tb = dateToTs(b);
  if (!ta || !tb) return null;
  return Math.round(Math.abs(tb - ta) / DAY_MS);
}

export function routeLabel(r: string | null): string {
  if (!r) return "";
  const v = r.toLowerCase();
  if (v.includes("two_week") || v.includes("2ww") || v === "urgent") {
    return "2WW urgent";
  }
  if (v === "routine") return "Routine";
  if (v.includes("emergency")) return "Emergency";
  return r;
}

export function outcomeLabel(o: string | null): string {
  if (!o) return "";
  const v = o.toLowerCase();
  if (v === "cancer") return "Cancer confirmed";
  if (v === "benign") return "Benign";
  if (v.includes("watch")) return "Watchful waiting";
  return o;
}

export function outcomeColor(o: string | null): string {
  const v = (o ?? "").toLowerCase();
  if (v === "cancer") return "#B91C1C";
  if (v === "benign") return "#047857";
  return "#475569";
}

/** Fit the track tightly around this episode's events (avoids a sparse mid-band). */
export function episodeTimeWindow(
  ep: EpisodeSummaryEpr,
  encounters: TimelineItem[],
): { minTs: number; maxTs: number } {
  const stamps = [
    dateToTs(ep.referral_date),
    dateToTs(ep.end_date),
    dateToTs(ep.first_presentation_date),
    ...encounters.map((e) => dateToTs(e.item_date)),
  ].filter((t) => t > 0);

  const now = Date.now();
  if (stamps.length === 0) {
    return { minTs: now - 7 * DAY_MS, maxTs: now + 7 * DAY_MS };
  }

  const pad = 3 * DAY_MS;
  let minTs = Math.min(...stamps) - pad;
  let maxTs = Math.max(...stamps, now) + pad;
  const minSpan = 14 * DAY_MS;
  if (maxTs - minTs < minSpan) {
    const mid = (minTs + maxTs) / 2;
    minTs = mid - minSpan / 2;
    maxTs = mid + minSpan / 2;
  }
  return { minTs, maxTs };
}
