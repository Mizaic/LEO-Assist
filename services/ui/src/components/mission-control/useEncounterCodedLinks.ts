/**
 * useEncounterCodedLinks -- per-encounter coded link cache. Lifted
 * out of EncounterTextTab to keep that file under the 500 LOC
 * static-source budget.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   DI: DI-LEO-AI-220, DI-LEO-AI-221
 */
"use client";

import { useCallback, useRef, useState } from "react";
import { fetchEncounterCodedLinks } from "@/lib/api";
import type { CodedLink } from "@/lib/types";

interface State {
  codedByEncounter: Record<string, CodedLink[]>;
  codingErrorByEncounter: Record<string, string>;
  codingLoadingFor: Record<string, boolean>;
}

export function useEncounterCodedLinks(patientId: string) {
  const [state, setState] = useState<State>({
    codedByEncounter: {},
    codingErrorByEncounter: {},
    codingLoadingFor: {},
  });
  const loadedRef = useRef<Set<string>>(new Set());
  const loadingRef = useRef<Set<string>>(new Set());

  const reset = useCallback(() => {
    loadedRef.current = new Set();
    loadingRef.current = new Set();
    setState({
      codedByEncounter: {},
      codingErrorByEncounter: {},
      codingLoadingFor: {},
    });
  }, []);

  const invalidate = useCallback((encounterId: string) => {
    const key = String(encounterId);
    loadedRef.current.delete(key);
  }, []);

  const clearLinks = useCallback((encounterId: string) => {
    const key = String(encounterId);
    loadedRef.current.delete(key);
    setState((prev) => ({
      ...prev,
      codedByEncounter: { ...prev.codedByEncounter, [key]: [] },
    }));
  }, []);

  const fetchFor = useCallback(
    async (encounterId: string) => {
      const key = String(encounterId);
      if (loadedRef.current.has(key) || loadingRef.current.has(key)) return;
      loadingRef.current.add(key);
      setState((prev) => ({
        ...prev,
        codingLoadingFor: { ...prev.codingLoadingFor, [key]: true },
        codingErrorByEncounter: { ...prev.codingErrorByEncounter, [key]: "" },
      }));
      try {
        const links = await fetchEncounterCodedLinks(patientId, key);
        loadedRef.current.add(key);
        setState((prev) => ({
          ...prev,
          codedByEncounter: { ...prev.codedByEncounter, [key]: links },
        }));
      } catch (e) {
        setState((prev) => ({
          ...prev,
          codingErrorByEncounter: {
            ...prev.codingErrorByEncounter,
            [key]:
              e instanceof Error
                ? e.message
                : "Could not load coded concepts for this encounter.",
          },
        }));
      } finally {
        loadingRef.current.delete(key);
        setState((prev) => ({
          ...prev,
          codingLoadingFor: { ...prev.codingLoadingFor, [key]: false },
        }));
      }
    },
    [patientId]
  );

  return {
    ...state,
    reset,
    invalidate,
    clearLinks,
    fetchFor,
  };
}
