/**
 * Atlas trace:
 *   DO: DO-CFA1ED55, DO-9C9CB1D8
 *   DI: DI-340279C1, DI-6424B6FC, DI-10667413
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
import { useOrg, useOrgId } from "@/context/OrgContext";
import type { StatTile } from "@leo/design-system";

import {
  fetchTenantCompletenessDomains,
  type TenantCompletenessDomain,
} from "./tenantCompletenessApi";

export type SourceFilter = "all" | "nice" | "platform" | "tenant";

export function computeStats(
  domains: DomainSummary[],
  tenantCount = domains.filter((d) => d.source === "tenant").length,
): StatTile[] {
  const nice = domains.filter((d) => d.source === "nice").length;
  const platform = domains.filter((d) => d.source === "platform").length;
  return [
    { id: "total", label: "Areas", value: domains.length, hint: "All clinical areas LEO can audit" },
    { id: "nice", label: "From NICE", value: nice, hint: "Sourced from NICE guidelines", tone: nice > 0 ? "positive" : "neutral" },
    { id: "platform", label: "Built-in", value: platform, hint: "Shipped with LEO" },
    { id: "tenant", label: "Your organisation", value: tenantCount, hint: "Completeness domains for your organisation", tone: tenantCount > 0 ? "positive" : "neutral" },
  ];
}

export function useDomainsList() {
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();
  const organizationId = useOrgId();
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [tenantDomains, setTenantDomains] = useState<TenantCompletenessDomain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<DomainSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DomainSummary | null>(null);
  const [snackMsg, setSnackMsg] = useState<string | null>(null);

  const loadDomains = useLoadDomains({
    sourceFilter,
    organizationId,
    setDomains,
    setTenantDomains,
    setLoading,
    setError,
  });
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

  const view = useDomainsView(domains, tenantDomains, searchText);
  const showCreateButton = isPlatformAdmin && sourceFilter === "all";

  return {
    router,
    isPlatformAdmin,
    sourceFilter,
    setSourceFilter,
    domains,
    tenantDomains,
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
    showCreateButton,
    ...view,
    ...actions,
  };
}

function useDomainsView(
  domains: DomainSummary[],
  tenantDomains: TenantCompletenessDomain[],
  searchText: string,
) {
  const filtered = useMemo(() => filterDomains(domains, searchText), [domains, searchText]);
  const filteredTenant = useMemo(
    () => filterTenantDomains(tenantDomains, searchText),
    [tenantDomains, searchText],
  );
  const stats = useMemo(
    () => computeStats(domains, tenantDomains.length),
    [domains, tenantDomains.length],
  );
  return {
    filtered,
    filteredTenant,
    stats,
    counts: {
      nice: domains.filter((d) => d.source === "nice").length,
      platform: domains.filter((d) => d.source === "platform").length,
      tenant: tenantDomains.length,
      total: domains.length + tenantDomains.length,
    },
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

function filterTenantDomains(
  domains: TenantCompletenessDomain[],
  searchText: string,
): TenantCompletenessDomain[] {
  const q = searchText.trim().toLowerCase();
  if (!q) return domains;
  return domains.filter((d) => tenantDomainMatches(d, q));
}

function tenantDomainMatches(domain: TenantCompletenessDomain, q: string): boolean {
  if (domain.domain_name.toLowerCase().includes(q)) return true;
  if ((domain.organization_name ?? "").toLowerCase().includes(q)) return true;
  return domain.completeness_groups.some((g) => g.name.toLowerCase().includes(q));
}

type LoadDomainsArgs = {
  sourceFilter: SourceFilter;
  organizationId: string | undefined;
  setDomains: (next: DomainSummary[]) => void;
  setTenantDomains: (next: TenantCompletenessDomain[]) => void;
  setLoading: (next: boolean) => void;
  setError: (next: string | null) => void;
};

function useLoadDomains(args: LoadDomainsArgs) {
  const { organizationId, setDomains, setTenantDomains, setLoading, setError } = args;
  const loadDomains = useCallback(async (filter: SourceFilter) => {
    setLoading(true);
    setError(null);
    try {
      await loadDomainLists(filter, {
        sourceFilter: filter,
        organizationId,
        setDomains,
        setTenantDomains,
        setLoading,
        setError,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load domains");
    } finally {
      setLoading(false);
    }
  }, [organizationId, setDomains, setTenantDomains, setLoading, setError]);

  useEffect(() => {
    void loadDomains(args.sourceFilter);
  }, [loadDomains, args.sourceFilter]);

  return loadDomains;
}

async function loadDomainLists(filter: SourceFilter, args: LoadDomainsArgs) {
  const completenessPromise = fetchTenantCompletenessDomains(args.organizationId);
  if (filter === "tenant") {
    args.setTenantDomains(await completenessPromise);
    return;
  }
  const src = filter === "all" ? undefined : filter;
  const [knowledge, completeness] = await Promise.all([
    fetchDomains(src),
    completenessPromise,
  ]);
  args.setDomains(knowledge);
  args.setTenantDomains(completeness);
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
