/**
 * State and save/load helpers for Pipeline Guards.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { type RuleFormValues } from "@/components/workbench/RuleEditor";

import { GUARD_FAMILY_COPY, GUARD_FAMILY_KEYS } from "./guardFamilyCopy";
import type { NerGuardRule } from "./types";

async function fetchGuardRules(family: string): Promise<NerGuardRule[]> {
  const url = family === "all"
    ? "/api/admin/workbench/guard-rules"
    : `/api/admin/workbench/guard-rules?family=${family}`;
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

async function saveGuardRule(
  family: string,
  values: RuleFormValues,
  existingId?: string,
): Promise<void> {
  const body = { ...values, family, rule_id: existingId };
  const url = existingId
    ? `/api/admin/workbench/guard-rules/${existingId}`
    : "/api/admin/workbench/guard-rules";
  await fetch(url, {
    method: existingId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function matchesSearch(rule: NerGuardRule, query: string): boolean {
  if (!query) return true;
  const hay = `${rule.pattern} ${rule.family} ${rule.rule_type} ${rule.summary ?? ""}`;
  return hay.toLowerCase().includes(query);
}

function useFamilySelection() {
  const [openFamilyKey, setOpenFamilyKey] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<NerGuardRule | null>(null);
  const [addingNew, setAddingNew] = useState(false);
  return {
    openFamilyKey,
    selectedRule,
    addingNew,
    setOpenFamilyKey,
    setSelectedRule,
    setAddingNew,
    openFamily: (key: string, firstRule?: NerGuardRule | null) => {
      setAddingNew(false);
      setSelectedRule(firstRule ?? null);
      setOpenFamilyKey(key);
    },
    closeFamily: () => {
      setOpenFamilyKey(null);
      setSelectedRule(null);
    },
    selectRule: (rule: NerGuardRule) => {
      setAddingNew(false);
      setSelectedRule(rule);
    },
    startAdd: () => {
      setOpenFamilyKey(null);
      setSelectedRule(null);
      setAddingNew(true);
    },
    cancelAdd: () => setAddingNew(false),
    clearSelection: () => {
      setSelectedRule(null);
      setAddingNew(false);
    },
  };
}

export function useGuardRulesPage() {
  const searchParams = useSearchParams();
  const fired_rule_id = searchParams.get("fired_rule_id");
  const source_sentence = searchParams.get("source_sentence");
  const [search, setSearch] = useState(source_sentence ?? "");
  const [familyFilter, setFamilyFilter] = useState("all");
  const [rules, setRules] = useState<NerGuardRule[]>([]);
  const [saving, setSaving] = useState(false);
  const selection = useFamilySelection();
  const setSelectedRule = selection.setSelectedRule;
  const setOpenFamilyKey = selection.setOpenFamilyKey;

  const loadRules = useCallback(async () => {
    const data = await fetchGuardRules(familyFilter);
    setRules(data);
    if (!fired_rule_id) return;
    const match = data.find((r) => r.rule_id === fired_rule_id);
    if (!match) return;
    setSelectedRule(match);
    setOpenFamilyKey(match.family);
  }, [familyFilter, fired_rule_id, setOpenFamilyKey, setSelectedRule]);

  useEffect(() => { loadRules(); }, [loadRules]);

  const query = search.toLowerCase();
  const filtered = useMemo(
    () => rules.filter((rule) => matchesSearch(rule, query)),
    [rules, query],
  );
  const visibleKeys = familyFilter === "all" ? GUARD_FAMILY_KEYS : [familyFilter];
  const cards = visibleKeys.filter((key) => filtered.some((rule) => rule.family === key));
  const openCopy = selection.openFamilyKey
    ? GUARD_FAMILY_COPY[selection.openFamilyKey]
    : null;

  async function handleSave(values: RuleFormValues) {
    setSaving(true);
    try {
      const family = selection.selectedRule?.family
        ?? selection.openFamilyKey
        ?? (familyFilter !== "all" ? familyFilter : "scope_guard");
      await saveGuardRule(family, values, selection.selectedRule?.rule_id);
      selection.clearSelection();
      await loadRules();
    } finally {
      setSaving(false);
    }
  }

  return {
    search,
    setSearch,
    familyFilter,
    setFamilyFilter,
    rules,
    filtered,
    cards,
    openCopy,
    saving,
    handleSave,
    ...selection,
  };
}
