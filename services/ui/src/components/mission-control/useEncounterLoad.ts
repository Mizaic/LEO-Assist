import { useCallback, useEffect, useState } from "react";
import { fetchPatientEncounters } from "@/lib/missionControlApi";
import type { EncounterCardData } from "./EncounterCard";

// Loads a patient's encounters once on mount and exposes a refresh
// helper for after recode jobs. Lifted out of EncounterTextTab to
// keep that file under the 500 LOC ceiling.
//
// Design Controls: DI-LEO-AI-179, DO-LEO-AI-178.

export type Encounter = EncounterCardData;

export interface UseEncounterLoadResult {
  encounters: Encounter[];
  setEncounters: React.Dispatch<React.SetStateAction<Encounter[]>>;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<Encounter[]>;
}

export function useEncounterLoad(patientId: string): UseEncounterLoadResult {
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchPatientEncounters(patientId)
      .then(setEncounters)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load encounter text.")
      )
      .finally(() => setLoading(false));
  }, [patientId]);

  const refresh = useCallback(async () => {
    const refreshed = await fetchPatientEncounters(patientId);
    setEncounters(refreshed);
    return refreshed;
  }, [patientId]);

  return { encounters, setEncounters, loading, error, refresh };
}
