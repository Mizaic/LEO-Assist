/**
 * Load, search, and create product NCRs from Validation Lab.
 *
 * Atlas: DI-287FFFD0
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useEffect, useState } from "react";

import { createProductNcr, listProductNcrs } from "./clinicalNcrApi";
import {
  emptyNcrDraft,
  ncrDraftError,
  type NcrDraft,
  type ProductNcr,
} from "./ncrDraft";

export function useClinicalNcr(
  runId = "",
  why = "",
  onLinked?: (row: ProductNcr) => void,
) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<ProductNcr[]>([]);
  const [selected, setSelected] = useState<ProductNcr | null>(null);
  const [draft, setDraft] = useState<NcrDraft>(emptyNcrDraft);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadNcrs("", setRows, setBusy, setError);
  }, []);

  return {
    query,
    setQuery,
    rows,
    selected,
    setSelected,
    draft,
    setDraft,
    creating,
    setCreating,
    busy,
    error,
    onSearch: () => void loadNcrs(query, setRows, setBusy, setError),
    onCreate: () =>
      void saveNcr(draft, runId, why, {
        setBusy,
        setError,
        setSelected,
        setCreating,
        setDraft,
        setRows,
        onLinked,
      }),
  };
}

async function loadNcrs(
  query: string,
  setRows: (rows: ProductNcr[]) => void,
  setBusy: (busy: boolean) => void,
  setError: (error: string) => void,
) {
  setBusy(true);
  setError("");
  try {
    setRows(await listProductNcrs(query));
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : "Could not load NCRs");
  } finally {
    setBusy(false);
  }
}

async function saveNcr(
  draft: NcrDraft,
  runId: string,
  why: string,
  mut: {
    setBusy: (busy: boolean) => void;
    setError: (error: string) => void;
    setSelected: (row: ProductNcr | null) => void;
    setCreating: (value: boolean) => void;
    setDraft: (draft: NcrDraft) => void;
    setRows: (fn: (prev: ProductNcr[]) => ProductNcr[]) => void;
    onLinked?: (row: ProductNcr) => void;
  },
) {
  const problem = ncrDraftError(draft);
  if (problem) {
    mut.setError(problem);
    return;
  }
  mut.setBusy(true);
  mut.setError("");
  try {
    const created = await createProductNcr(draft, { runId, why });
    mut.setSelected(created);
    mut.onLinked?.(created);
    mut.setCreating(false);
    mut.setDraft(emptyNcrDraft());
    mut.setRows((prev) => [created, ...prev.filter((row) => row.id !== created.id)]);
  } catch (err: unknown) {
    mut.setError(err instanceof Error ? err.message : "Could not open that NCR");
  } finally {
    mut.setBusy(false);
  }
}
