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
  type ConceptMentionSourceType,
} from "@/lib/patientEprApi";

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** A mention's source type and id together are the only stable identity. */
function mentionKey(sourceType: ConceptMentionSourceType, sourceId: string): string {
  return `${sourceType}:${sourceId}`;
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
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, ConceptMentionDetail>>({});
  const [detailLoadingKey, setDetailLoadingKey] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadDetail = useCallback(
    async (sourceType: ConceptMentionSourceType, sourceId: string) => {
      const key = mentionKey(sourceType, sourceId);
      if (!conceptId || details[key]) return;
      setDetailLoadingKey(key);
      setDetailError(null);
      try {
        const detail = await fetchConceptMentionDetail(
          patientId,
          conceptId,
          sourceType,
          sourceId
        );
        setDetails((prev) => ({ ...prev, [key]: detail }));
      } catch (err) {
        setDetailError(errorMessage(err, "Unable to load this mention."));
      } finally {
        setDetailLoadingKey(null);
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
    } catch (err) {
      setMentionsError(errorMessage(err, "Unable to load evidence."));
    } finally {
      setMentionsLoading(false);
    }
  }, [conceptId, mentions, patientId]);

  const toggleMention = useCallback(
    (sourceType: ConceptMentionSourceType, sourceId: string) => {
      const key = mentionKey(sourceType, sourceId);
      const next = expandedKey === key ? null : key;
      setExpandedKey(next);
      if (next) void loadDetail(sourceType, sourceId);
    },
    [expandedKey, loadDetail]
  );

  return {
    mentions,
    mentionsLoading,
    mentionsError,
    expandedKey,
    details,
    detailLoadingKey,
    detailError,
    loadMentions,
    toggleMention,
    mentionKey,
  };
}
