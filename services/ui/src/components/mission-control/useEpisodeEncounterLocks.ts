/**
 * useEpisodeEncounterLocks -- pulls every VerificationLock on an
 * episode and indexes them by encounter id so EncounterTextTab can
 * render lock chips and disable the "Reset and recode" affordance on
 * locked encounters.
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/useEpisodeEncounterLocks.ts
 *   DI: DI-C424BB44 (VerificationLock primitive)
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 */
"use client";

import { useEffect, useState } from "react";
import {
  listLocksForEpisode,
  type VerificationLockSummary,
} from "@/lib/missionControlApi";

function indexByEncounter(
  locks: VerificationLockSummary[]
): Record<string, VerificationLockSummary> {
  const map: Record<string, VerificationLockSummary> = {};
  for (const lock of locks) {
    let encounterId: string | null = null;
    if (lock.entity_type === "encounter") encounterId = lock.entity_id;
    else if (
      lock.entity_type === "is_part_of_edge" ||
      lock.entity_type === "coded_link"
    ) {
      const [enc] = lock.entity_id.split(":");
      encounterId = enc || null;
    }
    if (encounterId && !map[encounterId]) {
      map[encounterId] = lock;
    }
  }
  return map;
}

export function useEpisodeEncounterLocks(
  episodeId: string
): Record<string, VerificationLockSummary> {
  const [locks, setLocks] = useState<Record<string, VerificationLockSummary>>(
    {}
  );
  useEffect(() => {
    let cancelled = false;
    let promise: Promise<unknown> | null = null;
    try {
      promise = listLocksForEpisode(episodeId);
    } catch {
      promise = Promise.resolve({ episode_id: episodeId, locks: [] });
    }
    Promise.resolve(promise)
      .then((res) => {
        if (cancelled) return;
        const summary = res as { locks?: VerificationLockSummary[] } | null;
        setLocks(indexByEncounter(summary?.locks ?? []));
      })
      .catch(() => {
        if (!cancelled) setLocks({});
      });
    return () => {
      cancelled = true;
    };
  }, [episodeId]);
  return locks;
}
