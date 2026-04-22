/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";
/**
 * useDualSaveAdapter -- bridges GoldLabelEditorDialog to the
 * dual-save backend (DI-LEO-AI-221).
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
import { useCallback, useEffect, useRef } from "react";

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

// Stable, order-insensitive key for a baseline so we can compare two
// baselines by value rather than by array identity (the host often
// re-supplies a fresh placeholder array on every render).
function baselineKey(ids: string[] | undefined): string {
  return [...(ids || [])]
    .map((id) => String(id).trim())
    .filter(Boolean)
    .sort()
    .join("|");
}

export function useDualSaveAdapter({
  labelId,
  context,
  onSynced,
}: UseDualSaveAdapterArgs): GoldDialogEntitySaver {
  const baselineRef = useRef<string[]>(context.baseline_concept_ids);
  // Track the encounter the ref currently belongs to. When the host
  // swaps to a different (patient, encounter) the ref must be re-seeded
  // from the freshly-fetched baseline; when the same encounter is
  // re-rendered (the common case), the ref is only allowed to grow
  // from empty to the first non-empty seed, after which only the API
  // response advances it.
  const seededForRef = useRef<string>("");
  const encounterKey = `${context.patient_id}::${context.encounter_id}`;
  const isPlaceholder = baselineKey(baselineRef.current).length === 0;
  const incomingHasContent =
    baselineKey(context.baseline_concept_ids).length > 0;

  // EncounterCard / EncounterPreviewDialog call this hook on every
  // render - first with a placeholder context whose
  // baseline_concept_ids is [], and again with the real seed once
  // /gold-labels/from-encounter resolves. useRef only honours its
  // initial value on the first render, so without this effect the ref
  // would stay at [] and the first save would POST an empty baseline,
  // hitting the optimistic-concurrency 409 every time.
  // Atlas: DI-85B110A5 / DO-30A82196 / VT-8DFB9DB8.
  useEffect(() => {
    const switchedEncounter = seededForRef.current !== encounterKey;
    if (switchedEncounter) {
      // Only re-seed once the host has supplied the real baseline for
      // the new encounter; until then keep the ref empty so a save
      // attempted in the gap would still surface a 409 rather than
      // silently overwrite.
      if (incomingHasContent) {
        baselineRef.current = context.baseline_concept_ids;
        seededForRef.current = encounterKey;
      } else {
        baselineRef.current = [];
      }
    } else if (isPlaceholder && incomingHasContent) {
      baselineRef.current = context.baseline_concept_ids;
      seededForRef.current = encounterKey;
    }
  }, [
    encounterKey,
    isPlaceholder,
    incomingHasContent,
    context.baseline_concept_ids,
  ]);

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
      seededForRef.current = `${context.patient_id}::${context.encounter_id}`;
      onSynced?.(result);
    },
    [labelId, context.patient_id, context.encounter_id, onSynced],
  );
}
