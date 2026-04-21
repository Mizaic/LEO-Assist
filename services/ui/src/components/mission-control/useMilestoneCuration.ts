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
import type { MissionEpisode } from "@/lib/missionControlApi";
import type { MilestoneCurationEncounter } from "./MilestoneCurationParts";
import type { Encounter } from "./useEncounterLoad";

interface MilestoneLookupEntry {
  episodeId: string;
  milestoneType: string;
}

/** Builds a lookup of encounter_id -> {episodeId, milestoneType} for
 *  every encounter linked into any episode milestone slot. Used by
 *  EncounterCard so it can render "Linked: <slot>" instead of "Add to
 *  milestone" when the encounter already fills a slot. */
export function buildMilestoneLookup(
  episodes: MissionEpisode[]
): Map<string, MilestoneLookupEntry> {
  const map = new Map<string, MilestoneLookupEntry>();
  episodes.forEach((ep) => {
    (ep.milestones ?? []).forEach((m) => {
      if (!m.encounter_id) return;
      const key = String(m.encounter_id);
      if (map.has(key)) return;
      map.set(key, {
        episodeId: ep.episode_id,
        milestoneType: m.milestone_type,
      });
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
