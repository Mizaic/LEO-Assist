/**
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { StatTile } from "@leo/design-system";

import { getLabResultConfig, listLabResultConfigs } from "./api";
import type { LabResultConfig, LabResultConfigSummary } from "./types";

export function useLabResultsList() {
  const [allItems, setAllItems] = useState<LabResultConfigSummary[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<LabResultConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLabResultConfigs("");
      setAllItems(data.items || []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load lab configs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const items = useMemo(() => filterItems(allItems, query), [allItems, query]);
  const handleRowClick = useOpenRow(setError, setSelected);
  const refreshSelected = useRefreshSelected(selected, setSelected, loadList);
  const stats = useMemo(() => buildStats(allItems), [allItems]);

  const onCreated = async (id: string) => {
    setAddOpen(false);
    await loadList();
    const data = await getLabResultConfig(id);
    setSelected(data.item);
    setToast("Observable added.");
  };

  const emptyState = emptyCopy(loading, query);

  return {
    query,
    setQuery,
    selected,
    setSelected,
    error,
    setError,
    addOpen,
    setAddOpen,
    toast,
    setToast,
    items,
    stats,
    emptyState,
    handleRowClick,
    refreshSelected,
    onCreated,
  };
}

export type LabResultsList = ReturnType<typeof useLabResultsList>;

function filterItems(allItems: LabResultConfigSummary[], query: string) {
  if (!query.trim()) return allItems;
  const q = query.toLowerCase();
  return allItems.filter(
    (i) =>
      i.display_name.toLowerCase().includes(q) ||
      i.concept_id.toLowerCase().includes(q),
  );
}

function useOpenRow(
  setError: (next: string | null) => void,
  setSelected: (next: LabResultConfig) => void,
) {
  return useCallback(async (row: LabResultConfigSummary) => {
    setError(null);
    try {
      const data = await getLabResultConfig(row.concept_id);
      setSelected(data.item);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load config.");
    }
  }, [setError, setSelected]);
}

function useRefreshSelected(
  selected: LabResultConfig | null,
  setSelected: (next: LabResultConfig) => void,
  loadList: () => Promise<void>,
) {
  return useCallback(async () => {
    if (selected) {
      const data = await getLabResultConfig(selected.concept_id);
      setSelected(data.item);
    }
    await loadList();
  }, [selected, setSelected, loadList]);
}

function buildStats(allItems: LabResultConfigSummary[]): StatTile[] {
  const missing = (key: "range_count" | "conversion_count" | "interpretation_count") =>
    allItems.filter((i) => !(i[key] ?? 0)).length;
  return [
    { id: "total", label: "Configured observables", value: allItems.length },
    {
      id: "no-ranges",
      label: "Missing ranges",
      value: missing("range_count"),
      tone: missing("range_count") ? "warning" : "positive",
    },
    {
      id: "no-conversions",
      label: "Missing conversions",
      value: missing("conversion_count"),
      tone: missing("conversion_count") ? "warning" : "positive",
    },
    {
      id: "no-interpretations",
      label: "Missing interpretations",
      value: missing("interpretation_count"),
      tone: missing("interpretation_count") ? "warning" : "positive",
    },
  ];
}

function emptyCopy(loading: boolean, query: string): string {
  if (loading) return "Loading observables...";
  if (query) return "No observables match this search.";
  return "No observables configured yet. Click \"Add observable\" to create the first one.";
}
