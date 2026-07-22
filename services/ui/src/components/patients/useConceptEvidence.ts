/**
 * State + fetch logic for the problem-list chip evidence popover.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 */
"use client";

import { useCallback, useState } from "react";
import {
  fetchConceptMentionDetail,
  fetchConceptMentions,
  type ConceptMention,
  type ConceptMentionDetail,
} from "@/lib/patientEprApi";

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/**
 * Lazily loads dated mentions for a concept, then lazily loads the full
 * evidence sentence for whichever date the clinician expands. Keeps the
 * initial popover payload light: no sentence text is fetched until asked
 * for.
 */
export function useConceptEvidence(patientId: string, conceptId: string | null) {
  const [mentions, setMentions] = useState<ConceptMention[] | null>(null);
  const [mentionsLoading, setMentionsLoading] = useState(false);
  const [mentionsError, setMentionsError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, ConceptMentionDetail>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadDetail = useCallback(
    async (encounterId: string) => {
      if (!conceptId || details[encounterId]) return;
      setDetailLoadingId(encounterId);
      setDetailError(null);
      try {
        const detail = await fetchConceptMentionDetail(
          patientId,
          conceptId,
          encounterId
        );
        setDetails((prev) => ({ ...prev, [encounterId]: detail }));
      } catch (err) {
        setDetailError(errorMessage(err, "Unable to load this mention."));
      } finally {
        setDetailLoadingId(null);
      }
    },
    [conceptId, details, patientId]
  );

  const loadMentions = useCallback(async () => {
    if (!conceptId || mentions !== null) return;
    setMentionsLoading(true);
    setMentionsError(null);
    try {
      const rows = await fetchConceptMentions(patientId, conceptId);
      setMentions(rows);
      if (rows.length === 1) {
        setExpandedId(rows[0].encounter_id);
        void loadDetail(rows[0].encounter_id);
      }
    } catch (err) {
      setMentionsError(errorMessage(err, "Unable to load evidence."));
    } finally {
      setMentionsLoading(false);
    }
  }, [conceptId, mentions, patientId, loadDetail]);

  const toggleDate = useCallback(
    (encounterId: string) => {
      const next = expandedId === encounterId ? null : encounterId;
      setExpandedId(next);
      if (next) void loadDetail(next);
    },
    [expandedId, loadDetail]
  );

  return {
    mentions,
    mentionsLoading,
    mentionsError,
    expandedId,
    details,
    detailLoadingId,
    detailError,
    loadMentions,
    toggleDate,
  };
}
