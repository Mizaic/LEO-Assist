/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useEffect, useState } from "react";
import type { EngineerStep } from "./EngineerPanes";
import {
  loadWorkPhrase,
  refreshWorkPhrase,
  type UncodedPhrase,
  type WorkFixKind,
} from "./workFixApi";

export interface EngineerPanelInput {
  entityText: string;
  entityLabel?: string;
  reviewId?: string | null;
  encounterText?: string;
  extractionSource?: string;
  onFixed?: (kind: WorkFixKind) => void;
}

export function useEngineerPanel(props: EngineerPanelInput) {
  const [step, setStep] = useState<EngineerStep>("debug");
  const [mode, setMode] = useState<WorkFixKind | "idle">("idle");
  const [phrase, setPhrase] = useState(props.entityText);
  const [row, setRow] = useState<UncodedPhrase | null>(null);
  const [contextPhrase, setContextPhrase] = useState("");
  const [category, setCategory] = useState("NEGATED_EXISTENCE");
  const [direction, setDirection] = useState("FORWARD");
  const action = usePanelAction(phrase, props.entityText, setRow);

  useEffect(() => {
    setPhrase(props.entityText);
  }, [props.entityText]);
  useLoadPhrase(props, setRow);

  return {
    ...props,
    step,
    setStep,
    mode,
    setMode,
    phrase,
    setPhrase,
    row,
    contextPhrase,
    setContextPhrase,
    category,
    setCategory,
    direction,
    setDirection,
    ...action,
  };
}

function useLoadPhrase(
  props: EngineerPanelInput,
  setRow: (row: UncodedPhrase | null) => void,
) {
  useEffect(() => {
    let cancelled = false;
    loadWorkPhrase({
      phrase: props.entityText,
      entityLabel: props.entityLabel,
      encounterText: props.encounterText,
      extractedSource: props.extractionSource,
    })
      .then((next) => {
        if (!cancelled) setRow(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [
    props.entityText,
    props.entityLabel,
    props.encounterText,
    props.extractionSource,
    setRow,
  ]);
}

function usePanelAction(
  phrase: string,
  entityText: string,
  setRow: (row: UncodedPhrase | null) => void,
) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function runAction(action: () => Promise<void>, done?: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      const next = await refreshWorkPhrase(phrase || entityText).catch(() => null);
      if (next) setRow(next);
      setNotice(done || "Saved as a draft. Submit it for review next.");
    } catch (err) {
      const fallback = "Could not save. Please try again.";
      setError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  return { busy, notice, error, runAction };
}
