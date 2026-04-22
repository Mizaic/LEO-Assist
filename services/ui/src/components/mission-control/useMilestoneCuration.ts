/**
 * useMilestoneCuration -- computes the props needed by
 * MilestoneCurationDialog when a reviewer clicks the
 * "Add to milestone" / "Linked: <slot>" button on an
 * EncounterCard.
 *
 * Atlas trace:
 *   DO: DO-7986A957
 *   DI: DI-4B99678C
 */
"use client";

import { useCallback, useMemo, useState } from "react";
import {
  detachEncounterFromEpisode,
  type MissionEpisode,
} from "@/lib/missionControlApi";
import { STATUS_REVIEW, normaliseStatus } from "@/lib/episodeLifecycle";
import type { MilestoneCurationEncounter } from "./MilestoneCurationParts";
import type { Encounter } from "./useEncounterLoad";

export interface MilestoneLookupEntry {
  episodeId: string;
  milestoneType: string;
}

/** Per-episode roll-up used by EncounterCard's episode chips
 *  (DI-5159A336): one entry per episode the encounter is linked to,
 *  with every milestone slot it fills on that episode. The chip
 *  shows the episode label and lets the curator unlink the encounter
 *  from THAT episode entirely (all slots in one go). */
export interface EncounterEpisodeLink {
  episodeId: string;
  episodeLabel: string;
  milestoneTypes: string[];
}

/** Builds a lookup of encounter_id -> MilestoneLookupEntry[] covering
 *  EVERY milestone slot the encounter fills. One encounter can fill
 *  multiple slots on the same episode (for example a GP 2WW
 *  consultation that is both first_presentation and referral) --
 *  DI-F5E030ED. EncounterCard reads the array length to decide
 *  between "Add to milestone", "Linked: <slot>", and
 *  "Linked: <slot> + <slot>". */
export function buildMilestoneLookup(
  episodes: MissionEpisode[]
): Map<string, MilestoneLookupEntry[]> {
  const map = new Map<string, MilestoneLookupEntry[]>();
  episodes.forEach((ep) => {
    (ep.milestones ?? []).forEach((m) => {
      if (!m.encounter_id) return;
      const key = String(m.encounter_id);
      const entry: MilestoneLookupEntry = {
        episodeId: ep.episode_id,
        milestoneType: m.milestone_type,
      };
      const bucket = map.get(key);
      if (!bucket) {
        map.set(key, [entry]);
        return;
      }
      // Deduplicate on (episodeId, milestoneType) because the same
      // milestone can occasionally appear twice in the milestones
      // array when the upstream derives both date and encounter
      // rollups from the same edge.
      const already = bucket.some(
        (e) =>
          e.episodeId === entry.episodeId &&
          e.milestoneType === entry.milestoneType
      );
      if (!already) bucket.push(entry);
    });
  });
  return map;
}

/** Plain-English episode label for the chip ("Lung pathway, ref 14
 *  Jul 25", "Pathway in review, ref 02 Apr 25", or just "Pathway"
 *  when no metadata is available). Kept short -- the chip lives
 *  next to the milestone slot button in a dense action row. */
export function episodeChipLabel(ep: {
  cancer_type?: string | null;
  condition_type?: string | null;
  status?: string | null;
  referral_date?: string | null;
}): string {
  const cancer = (ep.cancer_type ?? "").trim();
  const condition = (ep.condition_type ?? "").trim();
  const canonicalStatus = normaliseStatus(ep.status ?? null);
  const head = cancer
    ? `${cancer} pathway`
    : condition
      ? `${condition} pathway`
      : canonicalStatus === STATUS_REVIEW
        ? "Pathway in review"
        : "Pathway";
  if (!ep.referral_date) return head;
  const day = String(ep.referral_date).slice(0, 10);
  return `${head}, ref ${shortDay(day)}`;
}

function shortDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
  });
}

/** Builds a per-encounter rollup of episode -> milestone slots.
 *  EncounterCard renders one chip per episode. Episodes with zero
 *  slots for the encounter are still included if they appear in
 *  `linked_encounter_ids` (a curator can link an encounter to an
 *  episode without filling a slot via legacy data, although the new
 *  manual flow always picks a slot). DI-5159A336. */
export function buildEncounterEpisodeLinks(
  episodes: MissionEpisode[]
): Map<string, EncounterEpisodeLink[]> {
  const map = new Map<string, EncounterEpisodeLink[]>();
  episodes.forEach((ep) => {
    const label = episodeChipLabel(ep);
    const perEncounter = new Map<string, Set<string>>();
    (ep.milestones ?? []).forEach((m) => {
      if (!m.encounter_id) return;
      const key = String(m.encounter_id);
      const slots = perEncounter.get(key) ?? new Set<string>();
      slots.add(m.milestone_type);
      perEncounter.set(key, slots);
    });
    perEncounter.forEach((slots, encounterId) => {
      if (slots.size === 0) return;
      const entry: EncounterEpisodeLink = {
        episodeId: ep.episode_id,
        episodeLabel: label,
        milestoneTypes: Array.from(slots).sort(),
      };
      const bucket = map.get(encounterId);
      if (bucket) bucket.push(entry);
      else map.set(encounterId, [entry]);
    });
  });
  return map;
}

function isoDay(value: string | null | undefined): string {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function toCurationEncounter(enc: Encounter): MilestoneCurationEncounter {
  return {
    encounter_id: String(enc.encounter_id),
    date: enc.date ?? null,
    text: enc.text ?? null,
  };
}

/** Per-encounter episode-chip wiring: lookup of links and a stable
 *  unlink handler that removes every IS_PART_OF edge between the
 *  encounter and the chosen episode in one call (DI-5159A336).
 *  Lives here so EncounterTextTab stays under the 500-LOC limit. */
export function useEncounterEpisodeChips(
  episodes: MissionEpisode[],
  onChanged: () => void | Promise<void>
) {
  const lookup = useMemo(() => buildEncounterEpisodeLinks(episodes), [episodes]);
  const unlink = useCallback(
    async (encounterId: string, episodeId: string) => {
      try {
        await detachEncounterFromEpisode(episodeId, encounterId);
      } catch (err) {
        // Idempotency: if the edge has already been removed (e.g. by a
        // concurrent milestone curation in the same drawer), the
        // backend returns 404 with detail "No IS_PART_OF edge between
        // encounter and episode". The desired post-condition -- no
        // edge between this encounter and this episode -- is already
        // true, so we treat it as success and refresh so the stale
        // chip disappears. Any other failure rethrows.
        if (!isAlreadyDetached(err)) throw err;
      }
      await onChanged();
    },
    [onChanged]
  );
  return { lookup, unlink };
}

function isAlreadyDetached(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message || "";
  return (
    msg.includes("No IS_PART_OF edge") ||
    msg.includes("(404)") ||
    msg.includes("404")
  );
}

export function useMilestoneCuration(encounters: Encounter[]) {
  const [target, setTarget] = useState<Encounter | null>(null);

  const open = useCallback((enc: Encounter) => setTarget(enc), []);
  const close = useCallback(() => setTarget(null), []);

  const sameDayEncounters = useMemo<MilestoneCurationEncounter[]>(() => {
    if (!target) return [];
    const day = isoDay(target.date);
    if (!day) return [toCurationEncounter(target)];
    return encounters
      .filter((e) => isoDay(e.date) === day)
      .map(toCurationEncounter);
  }, [target, encounters]);

  const triggerEncounter = useMemo<MilestoneCurationEncounter | null>(
    () => (target ? toCurationEncounter(target) : null),
    [target]
  );

  return { target, open, close, triggerEncounter, sameDayEncounters };
}
