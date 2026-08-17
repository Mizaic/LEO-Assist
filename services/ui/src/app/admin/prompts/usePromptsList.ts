/**
 * Atlas trace:
 *   DO: DO-BCD21209
 *   DI: DI-553F50A2, DI-C5A523A7
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { sortByIsoDateDesc } from "@/lib/dateSort";
import { api } from "@/lib/api";
import {
  CATEGORY_ALL,
  categoriseFromPrompt,
  humanName,
  type PromptConfig,
} from "./promptCategories";

export function usePromptsList() {
  const searchParams = useSearchParams();
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(searchParams.get("prompt_name") || "");
  const [activeCategory, setActiveCategory] = useState<string>(CATEGORY_ALL);

  useEffect(() => {
    api
      .get<{ prompts: PromptConfig[] }>("/api/prompts")
      .then((d) => setPrompts(d.prompts || []))
      .catch((err) => setError(err?.message ?? "Failed to load prompts"))
      .finally(() => setLoading(false));
  }, []);

  const allCategories = useMemo(() => {
    const cats = Array.from(
      new Set(prompts.map((p) => categoriseFromPrompt(p).label)),
    ).sort();
    return [CATEGORY_ALL, ...cats];
  }, [prompts]);

  const filtered = useMemo(() => filterPrompts(prompts, search, activeCategory), [
    prompts,
    activeCategory,
    search,
  ]);
  const grouped = useMemo(() => groupPrompts(filtered), [filtered]);
  const isFiltering = search.trim() !== "" || activeCategory !== CATEGORY_ALL;

  return {
    prompts,
    loading,
    error,
    setError,
    search,
    setSearch,
    activeCategory,
    setActiveCategory,
    allCategories,
    filtered,
    grouped,
    isFiltering,
  };
}

function filterPrompts(
  prompts: PromptConfig[],
  search: string,
  activeCategory: string,
): PromptConfig[] {
  const q = search.trim().toLowerCase();
  const f = prompts.filter((p) => {
    const matchCat =
      activeCategory === CATEGORY_ALL ||
      categoriseFromPrompt(p).label === activeCategory;
    const matchSearch =
      !q ||
      humanName(p.name).toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q);
    return matchCat && matchSearch;
  });
  return sortByIsoDateDesc(f, (p) => p.updatedAt);
}

function groupPrompts(filtered: PromptConfig[]): Array<[string, PromptConfig[]]> {
  const map = filtered.reduce<Record<string, PromptConfig[]>>((acc, p) => {
    const cat = categoriseFromPrompt(p).label;
    (acc[cat] ??= []).push(p);
    return acc;
  }, {});
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
}
