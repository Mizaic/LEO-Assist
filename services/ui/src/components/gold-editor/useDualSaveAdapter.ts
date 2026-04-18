"use client";
/**
 * useDualSaveAdapter -- bridges GoldLabelEditorDialog to the
 * dual-save backend (DI-LEO-AI-210).
 *
 * Returns an entitySaver function that the dialog calls in place of
 * the default PATCH on the gold label. This adapter posts to
 * /patients/{p}/encounters/{e}/coded-links/sync-from-gold which
 *   - writes/updates/deletes :DOCUMENTS rels on the live encounter
 *   - mirrors the same entity array onto the linked GoldLabel
 *   - returns a 409 Conflict if the live baseline_concept_ids drifted
 *
 * The adapter also tracks the last-known baseline_concept_ids so the
 * next save uses the freshly-applied set as its optimistic-concurrency
 * baseline.
 */
import { useCallback, useRef } from "react";

import { syncCodedLinksFromGold } from "./api";
import type {
  DualSaveEncounterContext,
  GoldDialogEntitySaver,
  SavedGoldEntity,
} from "./types";

export interface UseDualSaveAdapterArgs {
  labelId: string;
  context: DualSaveEncounterContext;
  onSynced?: (result: {
    live_links_added: number;
    live_links_removed: number;
    live_links_updated: number;
    baseline_concept_ids: string[];
  }) => void;
}

export function useDualSaveAdapter({
  labelId,
  context,
  onSynced,
}: UseDualSaveAdapterArgs): GoldDialogEntitySaver {
  const baselineRef = useRef<string[]>(context.baseline_concept_ids);

  return useCallback(
    async (entities: SavedGoldEntity[]) => {
      const result = await syncCodedLinksFromGold({
        patient_id: context.patient_id,
        encounter_id: context.encounter_id,
        label_id: labelId,
        expected_baseline_concept_ids: baselineRef.current,
        entities,
      });
      baselineRef.current = result.baseline_concept_ids;
      onSynced?.(result);
    },
    [labelId, context.patient_id, context.encounter_id, onSynced],
  );
}
