/**
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1, DI-6424B6FC
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  fetchDomains,
  createDomain,
  updateDomain,
  deleteDomain,
  type DomainSummary,
} from "@/lib/analyticsApi";
import { useOrg } from "@/context/OrgContext";
import type { StatTile } from "@leo/design-system";

export type SourceFilter = "all" | "nice" | "platform" | "tenant";

export function computeStats(domains: DomainSummary[]): StatTile[] {
  const nice = domains.filter((d) => d.source === "nice").length;
  const platform = domains.filter((d) => d.source === "platform").length;
  const tenant = domains.filter((d) => d.source === "tenant").length;
  return [
    { id: "total", label: "Areas", value: domains.length, hint: "All clinical areas LEO can audit" },
    { id: "nice", label: "From NICE", value: nice, hint: "Sourced from NICE guidelines", tone: nice > 0 ? "positive" : "neutral" },
    { id: "platform", label: "Built-in", value: platform, hint: "Shipped with LEO" },
    { id: "tenant", label: "Your organisation", value: tenant, hint: "Created by your admins", tone: tenant > 0 ? "positive" : "neutral" },
  ];
}

export function useDomainsList() {
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<DomainSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DomainSummary | null>(null);
  const [snackMsg, setSnackMsg] = useState<string | null>(null);

  const loadDomains = useLoadDomains(sourceFilter, setDomains, setLoading, setError);
  const actions = useDomainActions({
    router,
    sourceFilter,
    loadDomains,
    setError,
    setCreateOpen,
    setEditTarget,
    setDeleteTarget,
    setSnackMsg,
  });

  const filtered = useMemo(() => filterDomains(domains, searchText), [domains, searchText]);
  const stats = useMemo(() => computeStats(domains), [domains]);
  const showCreateButton =
    isPlatformAdmin && (sourceFilter === "all" || sourceFilter === "tenant");

  return {
    router,
    isPlatformAdmin,
    sourceFilter,
    setSourceFilter,
    domains,
    loading,
    error,
    setError,
    searchText,
    setSearchText,
    createOpen,
    setCreateOpen,
    editTarget,
    setEditTarget,
    deleteTarget,
    setDeleteTarget,
    snackMsg,
    setSnackMsg,
    loadDomains,
    filtered,
    showCreateButton,
    stats,
    counts: {
      nice: domains.filter((d) => d.source === "nice").length,
      platform: domains.filter((d) => d.source === "platform").length,
      tenant: domains.filter((d) => d.source === "tenant").length,
      total: domains.length,
    },
    ...actions,
  };
}

function filterDomains(domains: DomainSummary[], searchText: string): DomainSummary[] {
  const q = searchText.trim().toLowerCase();
  if (!q) return domains;
  return domains.filter(
    (d) =>
      d.name.toLowerCase().includes(q) ||
      (d.description ?? "").toLowerCase().includes(q),
  );
}

function useLoadDomains(
  sourceFilter: SourceFilter,
  setDomains: (next: DomainSummary[]) => void,
  setLoading: (next: boolean) => void,
  setError: (next: string | null) => void,
) {
  const loadDomains = useCallback(async (filter: SourceFilter) => {
    setLoading(true);
    setError(null);
    try {
      const src = filter === "all" ? undefined : filter;
      setDomains(await fetchDomains(src));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load domains");
    } finally {
      setLoading(false);
    }
  }, [setDomains, setLoading, setError]);

  useEffect(() => {
    void loadDomains(sourceFilter);
  }, [loadDomains, sourceFilter]);

  return loadDomains;
}

function useDomainActions(args: {
  router: ReturnType<typeof useRouter>;
  sourceFilter: SourceFilter;
  loadDomains: (filter: SourceFilter) => Promise<void>;
  setError: (next: string | null) => void;
  setCreateOpen: (next: boolean) => void;
  setEditTarget: (next: DomainSummary | null) => void;
  setDeleteTarget: (next: DomainSummary | null) => void;
  setSnackMsg: (next: string | null) => void;
}) {
  const handleCreate = useCallback(async (name: string, description: string) => {
    const d = await createDomain(name, description);
    args.setCreateOpen(false);
    args.setSnackMsg("Domain created");
    args.router.push(`/settings/domains/${d.id}`);
  }, [args]);

  const handleEdit = useCallback(async (id: string, name: string, description: string) => {
    await updateDomain(id, { name, description });
    args.setEditTarget(null);
    await args.loadDomains(args.sourceFilter);
  }, [args]);

  const handleDelete = useCallback(async (target: DomainSummary) => {
    args.setDeleteTarget(null);
    try {
      await deleteDomain(target.id);
      args.setSnackMsg("Domain deleted");
      await args.loadDomains(args.sourceFilter);
    } catch (e) {
      args.setError(e instanceof Error ? e.message : "Failed to delete domain");
    }
  }, [args]);

  const openEdit = useCallback((domain: DomainSummary) => {
    args.setEditTarget(domain);
  }, [args]);

  return { handleCreate, handleEdit, handleDelete, openEdit };
}

export type DomainsList = ReturnType<typeof useDomainsList>;
