/**
 * Autosave + resume helpers for RuleEditDraft (DI-D52E923B).
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  discardRuleEditDraft,
  draftReviewer,
  fetchRuleEditDraft,
  putRuleEditDraft,
  type RuleEditDraft,
  type RuleEditDraftWizardState,
} from "./ruleEditDraftApi";

const AUTOSAVE_MS = 15_000;

export interface DraftSnapshot {
  name: string;
  reason: string;
  logic_tree: Record<string, unknown>;
  actions: Array<Record<string, unknown>> | null;
  priority: string | null;
  due_days: number | null;
  is_default: boolean;
  wizard_state: RuleEditDraftWizardState;
}

interface Options {
  ruleId: string | null;
  open: boolean;
  dirty: boolean;
  buildSnapshot: () => DraftSnapshot | null;
}

export function useRuleEditDraft({
  ruleId,
  open,
  dirty,
  buildSnapshot,
}: Options) {
  const [pendingDraft, setPendingDraft] = useState<RuleEditDraft | null>(null);
  const [draftStatus, setDraftStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const buildRef = useRef(buildSnapshot);
  buildRef.current = buildSnapshot;
  const savingRef = useRef(false);

  useEffect(() => {
    if (!open || !ruleId) {
      setPendingDraft(null);
      setDraftStatus("idle");
      setDraftError(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const draft = await fetchRuleEditDraft(ruleId, draftReviewer());
        if (!cancelled) setPendingDraft(draft);
      } catch (err) {
        if (!cancelled) {
          setDraftError(
            err instanceof Error
              ? err.message
              : "Could not check for a saved draft.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, ruleId]);

  const saveProgress = useCallback(async (): Promise<boolean> => {
    if (!ruleId || savingRef.current) return false;
    const snapshot = buildRef.current();
    if (!snapshot) return false;
    savingRef.current = true;
    setDraftStatus("saving");
    setDraftError(null);
    try {
      const result = await putRuleEditDraft(ruleId, {
        reviewer: draftReviewer(),
        ...snapshot,
      });
      setDraftStatus("saved");
      setLastSavedAt(result.updated_at || new Date().toISOString());
      setPendingDraft(null);
      return true;
    } catch (err) {
      setDraftStatus("error");
      setDraftError(
        err instanceof Error ? err.message : "Could not save progress.",
      );
      return false;
    } finally {
      savingRef.current = false;
    }
  }, [ruleId]);

  useEffect(() => {
    if (!open || !ruleId || !dirty || pendingDraft) return;
    const timer = window.setInterval(() => {
      void saveProgress();
    }, AUTOSAVE_MS);
    return () => window.clearInterval(timer);
  }, [open, ruleId, dirty, pendingDraft, saveProgress]);

  const discardPending = useCallback(async () => {
    if (!ruleId) return;
    try {
      await discardRuleEditDraft(ruleId, draftReviewer());
      setPendingDraft(null);
      setDraftError(null);
    } catch (err) {
      setDraftError(
        err instanceof Error ? err.message : "Could not discard the draft.",
      );
    }
  }, [ruleId]);

  const clearPendingBanner = useCallback(() => {
    setPendingDraft(null);
  }, []);

  return {
    pendingDraft,
    draftStatus,
    draftError,
    lastSavedAt,
    saveProgress,
    discardPending,
    clearPendingBanner,
  };
}
