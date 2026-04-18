import { useCallback, useState } from "react";
import { resetAndRecodeEncounter } from "@/lib/missionControlApi";
import type { Encounter } from "./useEncounterLoad";
import {
  waitForRecodeProgress,
  type RecodeJobState,
} from "./encounterRecodeProgress";

// Encapsulates the per-encounter "Reset and recode" flow used by
// EncounterTextTab (queue, watch SSE progress, refresh until the
// encounter has freshly coded concepts). Lifted out so the main
// component stays under the 500 LOC ceiling.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-213, DO-LEO-AI-210,
// VT-LEO-AI-205.

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

interface UseEncounterRecodeArgs {
  patientId: string;
  refresh: () => Promise<Encounter[]>;
  onCleared: (encounterId: string) => void;
}

export interface UseEncounterRecodeResult {
  recodeMessage: string | null;
  recodeJobState: RecodeJobState;
  resettingEncounterId: string | null;
  start: (encounterId: string) => Promise<void>;
}

export function useEncounterRecode({
  patientId,
  refresh,
  onCleared,
}: UseEncounterRecodeArgs): UseEncounterRecodeResult {
  const [recodeMessage, setRecodeMessage] = useState<string | null>(null);
  const [recodeJobState, setRecodeJobState] = useState<RecodeJobState>(null);
  const [resettingEncounterId, setResettingEncounterId] = useState<string | null>(null);

  const start = useCallback(
    async (encounterId: string) => {
      setResettingEncounterId(encounterId);
      setRecodeMessage(null);
      try {
        const result = await resetAndRecodeEncounter(patientId, encounterId, false, false);
        onCleared(encounterId);
        setRecodeJobState("queued");
        setRecodeMessage(
          `Queued: ${result.links_deleted} coded links cleared. Run ${result.run_id.slice(0, 8)} is waiting for worker pickup.`
        );
        await waitForRecodeProgress(result.run_id, setRecodeJobState, setRecodeMessage);
        let latest = await refresh();
        for (let attempt = 0; attempt < 10; attempt += 1) {
          const target = latest.find((e) => String(e.encounter_id) === String(encounterId));
          if ((target?.coded_count ?? 0) > 0) {
            setRecodeMessage(
              `Completed: ${target?.coded_count ?? 0} coded concepts now linked to this encounter.`
            );
            break;
          }
          await sleep(2000);
          latest = await refresh();
        }
      } catch (e) {
        setRecodeJobState("failed");
        setRecodeMessage(
          e instanceof Error
            ? `Reset and recode failed: ${e.message}`
            : "Reset and recode failed."
        );
      } finally {
        setResettingEncounterId(null);
      }
    },
    [patientId, refresh, onCleared]
  );

  return { recodeMessage, recodeJobState, resettingEncounterId, start };
}
