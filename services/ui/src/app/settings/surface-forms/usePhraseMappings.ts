/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  fetchPhraseCounts,
  fetchPhraseMappings,
  publishPhrase,
  savePhraseDraft,
  sendBackPhrase,
  submitPhraseDrafts,
  type PhraseMappingCounts,
  type UncodedPhrase,
} from "./phraseMappingsApi";
import type { SnomedPick } from "./PhraseSnomedPicker";
import { draftNeedsTermFix } from "./termNeedsFix";

export type PhraseMode = "inbox" | "drafts" | "review" | "live";

const MODE_STATUS: Record<Exclude<PhraseMode, "live">, string> = {
  inbox: "inbox",
  drafts: "draft",
  review: "review",
};

const EMPTY_COUNTS: PhraseMappingCounts = {
  inbox: 0,
  draft: 0,
  review: 0,
  closed: 0,
  my_drafts: 0,
};

export function usePhraseMappings() {
  const [mode, setMode] = useState<PhraseMode>("inbox");
  const [counts, setCounts] = useState<PhraseMappingCounts>(EMPTY_COUNTS);
  const [items, setItems] = useState<UncodedPhrase[]>([]);
  const [selected, setSelected] = useState<UncodedPhrase | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshCounts = useCallback(async () => {
    try {
      setCounts({ ...EMPTY_COUNTS, ...(await fetchPhraseCounts()) });
    } catch {
      setCounts(EMPTY_COUNTS);
    }
  }, []);

  const loadQueue = useCallback(async (next: PhraseMode, keepKey?: string) => {
    if (next === "live") return;
    try {
      const page = await fetchPhraseMappings(MODE_STATUS[next]);
      const rows = page.items || [];
      setItems(rows);
      const kept = keepKey
        ? rows.find((row) => row.phrase_key === keepKey)
        : null;
      setSelected(kept || rows[0] || null);
    } catch (err) {
      setItems([]);
      setSelected(null);
      setError(err instanceof Error ? err.message : "Could not load phrases");
    }
  }, []);

  useEffect(() => {
    void refreshCounts();
    void loadQueue(mode);
  }, [mode, loadQueue, refreshCounts]);

  const handleSave = async (pick: SnomedPick | null, excludeReason: string) => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const exclude = !pick;
      await savePhraseDraft({
        phrase_key: selected.phrase_key,
        action: exclude ? "exclude" : "map",
        concept_id: pick?.concept_id,
        concept_term: pick?.term,
        reason: excludeReason,
      });
      setNotice("Draft saved. It is not live yet.");
      await refreshCounts();
      await loadQueue(mode, selected.phrase_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save draft");
    } finally {
      setSaving(false);
    }
  };

  const runAction = async (work: () => Promise<void>, fallback: string) => {
    setSaving(true);
    setError("");
    try {
      await work();
      await refreshCounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = () =>
    runAction(async () => {
      const blocked = items.filter(draftNeedsTermFix).length;
      if (blocked) {
        setError(
          `Fix the preferred term on ${blocked} draft${blocked === 1 ? "" : "s"} before submit.`,
        );
        return;
      }
      const result = await submitPhraseDrafts();
      setNotice(`Submitted ${result.submitted} draft(s) for review.`);
      await loadQueue("drafts");
    }, "Could not submit drafts");

  const handlePublish = () =>
    runAction(async () => {
      if (!selected) return;
      await publishPhrase(selected.phrase_key);
      setNotice("Published. The pipeline will use this from the next run.");
      await loadQueue("review");
    }, "Could not publish");

  const handleSendBack = () =>
    runAction(async () => {
      if (!selected) return;
      await sendBackPhrase(selected.phrase_key);
      await loadQueue("review");
    }, "Could not send back");

  return {
    mode,
    setMode,
    counts,
    items,
    selected,
    setSelected,
    saving,
    error,
    notice,
    handleSave,
    handleSubmit,
    handlePublish,
    handleSendBack,
  };
}
