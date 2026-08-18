/**
 * State and save/load helpers for Context Rules.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
 */
"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useSearchParams } from "next/navigation";

import { CATEGORY_KEYS, categoryCopyFor } from "./categoryCopy";
import type { NewContextRuleValues } from "./ContextAddDialog";
import type { ContextRule, FilterView } from "./types";

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const trimmed = text.trim();
    const isHtml = trimmed.startsWith("<!") || /^<html/i.test(trimmed);
    const detail = isHtml
      ? `Could not save (HTTP ${res.status}).`
      : `${res.status} ${trimmed || res.statusText}`;
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

function matchesSearch(rule: ContextRule, query: string): boolean {
  if (!query) return true;
  const hay = `${rule.literal} ${rule.description} ${rule.example} ${rule.category}`;
  return hay.toLowerCase().includes(query);
}

function filterRules(
  rules: ContextRule[],
  sourceFilter: FilterView,
  query: string,
): ContextRule[] {
  return rules.filter((rule) => {
    if (sourceFilter !== "all" && rule.source !== sourceFilter) return false;
    return matchesSearch(rule, query);
  });
}

function visibleCategoryKeys(filtered: ContextRule[]): string[] {
  const cards = CATEGORY_KEYS.filter((key) =>
    filtered.some((rule) => rule.category === key),
  );
  const extra = [...new Set(filtered.map((rule) => rule.category))].filter(
    (key) => !CATEGORY_KEYS.includes(key),
  );
  return [...cards, ...extra];
}

function useCategorySelection() {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<ContextRule | null>(null);
  const [adding, setAdding] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [deactivateTarget, setDeactivateTarget] = useState<ContextRule | null>(null);
  return {
    openKey,
    selectedRule,
    adding,
    saveError,
    setSaveError,
    deactivateTarget,
    setSelectedRule,
    setDeactivateTarget,
    open: (key: string, first?: ContextRule | null) => {
      setAdding(false);
      setOpenKey(key);
      setSelectedRule(first ?? null);
    },
    close: () => {
      setOpenKey(null);
      setSelectedRule(null);
    },
    startAdd: () => setAdding(true),
    cancelAdd: () => {
      setAdding(false);
      setSaveError("");
    },
  };
}

function useRulesLoader() {
  const [rules, setRules] = useState<ContextRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadRules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await jsonFetch<{ rules: ContextRule[] }>(
        "/api/training/context-rules?active_only=false&include_builtin=true",
      );
      setRules(data.rules ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { loadRules(); }, [loadRules]);
  return { rules, setRules, loading, error, setError, loadRules };
}

function useRuleWrites(
  loadRules: () => Promise<void>,
  setRules: Dispatch<SetStateAction<ContextRule[]>>,
  selection: ReturnType<typeof useCategorySelection>,
  setError: (value: string | null) => void,
) {
  const [saving, setSaving] = useState(false);
  async function handleAdd(values: NewContextRuleValues) {
    setSaving(true);
    selection.setSaveError("");
    try {
      await jsonFetch("/api/training/context-rules", {
        method: "POST",
        body: JSON.stringify(values),
      });
      selection.cancelAdd();
      await loadRules();
    } catch (e) {
      selection.setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  }
  async function handleDeactivate(ruleId: string) {
    try {
      await jsonFetch(`/api/training/context-rules/${ruleId}/deactivate`, {
        method: "PATCH",
      });
      setRules((prev) =>
        prev.map((r) => (r.rule_id === ruleId ? { ...r, active: false } : r)),
      );
      selection.setSelectedRule((prev) =>
        (prev?.rule_id === ruleId ? { ...prev, active: false } : prev),
      );
    } catch {
      setError("Could not deactivate rule. Please try again.");
    }
  }
  return { saving, handleAdd, handleDeactivate };
}

function useExportPdf(
  filtered: ContextRule[],
  sourceFilter: FilterView,
  setError: (value: string | null) => void,
) {
  const [exporting, setExporting] = useState(false);
  async function handleExportPdf() {
    setExporting(true);
    try {
      const { exportContextRulesPdf } = await import("@/lib/exportContextRulesPdf");
      exportContextRulesPdf(
        filtered.map((rule) => ({ ...rule, max_scope: rule.max_scope ?? 0 })),
        sourceFilter,
      );
    } catch (e) {
      setError(`PDF export failed: ${String(e)}`);
    } finally {
      setExporting(false);
    }
  }
  return { exporting, handleExportPdf };
}

export function useContextRulesPage() {
  const loader = useRulesLoader();
  const searchParams = useSearchParams();
  const termPrefill = searchParams.get("term") || "";
  const [search, setSearch] = useState(termPrefill);
  const [sourceFilter, setSourceFilter] = useState<FilterView>("all");
  const selection = useCategorySelection();
  const writes = useRuleWrites(
    loader.loadRules,
    loader.setRules,
    selection,
    loader.setError,
  );

  const query = search.toLowerCase();
  const filtered = useMemo(
    () => filterRules(loader.rules, sourceFilter, query),
    [loader.rules, sourceFilter, query],
  );
  const visibleKeys = visibleCategoryKeys(filtered);
  const openCopy = selection.openKey ? categoryCopyFor(selection.openKey) : null;
  const pdf = useExportPdf(filtered, sourceFilter, loader.setError);

  return {
    rules: loader.rules,
    filtered,
    visibleKeys,
    loading: loader.loading,
    error: loader.error,
    setError: loader.setError,
    search,
    setSearch,
    sourceFilter,
    setSourceFilter,
    openCopy,
    selectedRule: selection.selectedRule,
    adding: selection.adding,
    saving: writes.saving,
    saveError: selection.saveError,
    exporting: pdf.exporting,
    deactivateTarget: selection.deactivateTarget,
    setDeactivateTarget: selection.setDeactivateTarget,
    handleAdd: writes.handleAdd,
    handleDeactivate: writes.handleDeactivate,
    handleExportPdf: pdf.handleExportPdf,
    openCategory: selection.open,
    closeCategory: selection.close,
    selectRule: selection.setSelectedRule,
    startAdd: selection.startAdd,
    cancelAdd: selection.cancelAdd,
  };
}
