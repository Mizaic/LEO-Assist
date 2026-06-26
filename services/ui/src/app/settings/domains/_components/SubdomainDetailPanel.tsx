/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2340F614
 *   DI: DI-4885D9FF
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";

import CloseIcon from "@mui/icons-material/Close";

import { SegmentedTabs } from "@leo/design-system";

import {
  fetchSubdomain,
  saveCompletenessSchema,
  updateSubdomain,
  addConceptToSubdomain,
  removeConceptFromSubdomain,
  deleteSubdomain,
  exportSubdomain,
  fetchBenchmarkKeys,
  type SubdomainDetail,
  type CompletenessConceptGroup,
  type DomainUseCase,
} from "@/lib/analyticsApi";
import { searchTerms, fetchSemanticTags, fetchDescendants } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";
import { OverviewTab, ConceptsTab, RulesTab } from "./SubdomainPanelTabs";

type Tab = "overview" | "concepts" | "rules";

export interface SubdomainDetailPanelProps {
  domainId: string;
  subdomainName: string | null;
  canEditDomains: boolean;
  onClose: () => void;
  onDeleted: () => void;
}

type SearchHit = { snomed_concept_id: string; term: string; semantic_tag?: string; child_count?: number };
type DescRow = { snomed_concept_id: string; term: string; semantic_tag?: string; surface_form_count: number; surface_forms: string[] };
type DescPreview = { parentId: string; parentTerm: string; results: DescRow[] };

export default function SubdomainDetailPanel({
  domainId,
  subdomainName,
  canEditDomains,
  onClose,
  onDeleted,
}: SubdomainDetailPanelProps) {
  const [configSub, setConfigSub] = useState<SubdomainDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [snackMsg, setSnackMsg] = useState<string | null>(null);
  const [opError, setOpError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [allSemanticTags, setAllSemanticTags] = useState<string[]>([]);
  const [benchmarkKeys, setBenchmarkKeys] = useState<string[]>([]);
  const [exportLoading, setExportLoading] = useState<"concepts" | "expanded" | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchHit[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [descendantPreview, setDescendantPreview] = useState<DescPreview | null>(null);
  const [descendantLoading, setDescendantLoading] = useState<string | null>(null);
  const [descendantListOpen, setDescendantListOpen] = useState(false);
  const [pendingConcept, setPendingConcept] = useState<{ conceptId: number; term: string } | null>(null);
  const [addBenchmarkKey, setAddBenchmarkKey] = useState("");

  useEffect(() => {
    fetchSemanticTags().then(setAllSemanticTags).catch(() => {});
    fetchBenchmarkKeys().then(setBenchmarkKeys).catch(() => {});
  }, []);

  useEffect(() => {
    if (!subdomainName) { setConfigSub(null); return; }
    setConfigSub(null);
    setLoadError(null);
    setTab("overview");
    setSearchQuery("");
    setSearchResults([]);
    setDescendantPreview(null);
    setPendingConcept(null);
    setAddBenchmarkKey("");
    setOpError(null);
    fetchSubdomain(domainId, subdomainName)
      .then(setConfigSub)
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load subdomain"));
  }, [domainId, subdomainName]);

  const activeTags = configSub?.semantic_tags ?? [];
  const useCases: DomainUseCase[] = configSub?.use_cases ?? [];

  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (q.length < 2) { setSearchResults([]); return; }
    setSearchLoading(true);
    try {
      setSearchResults(await searchTerms(q, 15, activeTags.length > 0 ? activeTags : undefined));
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery, activeTags]);

  useEffect(() => {
    const t = setTimeout(() => void handleSearch(), 300);
    return () => clearTimeout(t);
  }, [handleSearch]);

  const handleUpdate = useCallback(async (updates: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
    assertion_filter?: string[];
    use_cases?: DomainUseCase[];
  }) => {
    if (!configSub) return;
    setSubmitting(true);
    try {
      const updated = await updateSubdomain(domainId, configSub.name, updates);
      setConfigSub((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          ...updated,
          concepts: prev.concepts,
          use_cases:
            (updated.use_cases?.length ?? 0) > 0
              ? updated.use_cases
              : (updates.use_cases ?? prev.use_cases),
        };
      });
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Failed to update subdomain");
    } finally {
      setSubmitting(false);
    }
  }, [domainId, configSub]);

  const handleSaveSchema = useCallback(async (schema: CompletenessConceptGroup[]) => {
    if (!configSub) return;
    await saveCompletenessSchema(domainId, configSub.name, schema);
    setConfigSub((prev) => prev ? { ...prev, completeness_schema: schema } : null);
    setSnackMsg("Rules saved");
  }, [domainId, configSub]);

  const handleAddConcept = async (conceptId: number, term: string, benchmarkKey?: string) => {
    if (!configSub) return;
    setSubmitting(true);
    try {
      setConfigSub(await addConceptToSubdomain(domainId, configSub.name, conceptId, term, [], benchmarkKey || undefined));
      setSearchQuery(""); setSearchResults([]); setPendingConcept(null); setAddBenchmarkKey("");
      setSnackMsg("Concept added");
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemoveConcept = async (conceptId: number) => {
    if (!configSub) return;
    setSubmitting(true);
    try {
      setConfigSub(await removeConceptFromSubdomain(domainId, configSub.name, conceptId));
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Failed to remove concept");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFetchDescendants = async (conceptId: string, term: string) => {
    if (!configSub) return;
    setDescendantLoading(conceptId);
    setDescendantPreview(null);
    try {
      const tags = activeTags.length > 0 ? activeTags : undefined;
      setDescendantPreview({ parentId: conceptId, parentTerm: term, results: await fetchDescendants(conceptId, 3, tags) });
    } catch {
      setOpError("Failed to fetch descendants");
    } finally {
      setDescendantLoading(null);
    }
  };

  const handleConfirmDescendants = async () => {
    if (!configSub || !descendantPreview) return;
    setSubmitting(true);
    try {
      setConfigSub(await addConceptToSubdomain(domainId, configSub.name, parseInt(descendantPreview.parentId, 10), descendantPreview.parentTerm, [], addBenchmarkKey || undefined));
      setDescendantPreview(null); setDescendantListOpen(false);
      setSearchQuery(""); setSearchResults([]); setAddBenchmarkKey("");
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setSubmitting(false);
    }
  };

  const handleExport = async (includeChildren: boolean) => {
    if (!configSub) return;
    setExportLoading(includeChildren ? "expanded" : "concepts");
    try {
      const data = await exportSubdomain(domainId, configSub.name, includeChildren);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = includeChildren ? `${configSub.name}-expanded.json` : `${configSub.name}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(null);
    }
  };

  const handleDeleteSubdomain = async () => {
    if (!configSub) return;
    try {
      await deleteSubdomain(domainId, configSub.name);
      onDeleted();
    } catch (e) {
      setOpError(e instanceof Error ? e.message : "Failed to delete subdomain");
    }
  };

  const existingConceptIds = useMemo(() => new Set(configSub?.concepts.map((c) => c.concept_id) ?? []), [configSub]);

  const searchPanelProps = {
    activeTags,
    benchmarkKeys,
    isAnalytics: useCases.includes("analytics"),
    searchQuery,
    onSearchQueryChange: setSearchQuery,
    searchResults,
    searchLoading,
    configSubmitting: submitting,
    existingConceptIds,
    descendantPreview,
    descendantLoading,
    descendantListOpen,
    onToggleDescendantList: () => setDescendantListOpen((o) => !o),
    pendingConcept,
    addBenchmarkKey,
    onAddBenchmarkKeyChange: setAddBenchmarkKey,
    onStartAddConcept: (conceptId: number, term: string) => { setPendingConcept({ conceptId, term }); setAddBenchmarkKey(""); setDescendantPreview(null); },
    onCancelPending: () => { setPendingConcept(null); setAddBenchmarkKey(""); },
    onFetchDescendants: handleFetchDescendants,
    onClearDescendantPreview: () => { setDescendantPreview(null); setDescendantListOpen(false); },
    onConfirmAddConcept: handleAddConcept,
    onConfirmDescendants: handleConfirmDescendants,
  };

  const tabs = [
    { id: "overview" as Tab, label: "Overview" },
    { id: "concepts" as Tab, label: "Concepts" },
    { id: "rules" as Tab, label: "Rules" },
  ];

  return (
    <Box sx={{ position: "sticky", top: 0, width: 440, flexShrink: 0, height: "calc(100vh - 140px)", overflowY: "auto", borderLeft: "1px solid #E2E8F0", bgcolor: "#FAFAFA", display: "flex", flexDirection: "column" }}>
      <Box sx={{ p: 2, borderBottom: "1px solid #E2E8F0", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
          {configSub?.name.replace(/_/g, " ") ?? (subdomainName ? "Loading..." : "")}
        </Typography>
        <IconButton size="small" aria-label="Close panel" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid #E2E8F0" }}>
        <SegmentedTabs tabs={tabs} value={tab} onChange={(id) => setTab(id as Tab)} aria-label="Subdomain configuration sections" />
      </Box>

      {loadError ? (
        <Alert severity="error" sx={{ m: 2 }}>{loadError}</Alert>
      ) : !configSub ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress size={24} aria-label="Loading subdomain" />
        </Box>
      ) : (
        <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
          {opError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setOpError(null)}>{opError}</Alert>}
          {tab === "overview" && (
            <OverviewTab
              configSub={configSub}
              allSemanticTags={allSemanticTags}
              canEditDomains={canEditDomains}
              submitting={submitting}
              onUpdate={handleUpdate}
              onClearSearch={() => setSearchResults([])}
              onSaved={() => setSnackMsg("Overview saved")}
            />
          )}
          {tab === "concepts" && (
            <ConceptsTab
              configSub={configSub}
              canEditDomains={canEditDomains}
              submitting={submitting}
              exportLoading={exportLoading}
              allSemanticTags={allSemanticTags}
              benchmarkKeys={benchmarkKeys}
              onExport={handleExport}
              onRemoveConcept={(id) => void handleRemoveConcept(id)}
              searchPanelProps={searchPanelProps}
            />
          )}
          {tab === "rules" && (
            <RulesTab
              schema={configSub.completeness_schema ?? []}
              subdomainConcepts={configSub.concepts ?? []}
              canEditDomains={canEditDomains}
              allSemanticTags={allSemanticTags}
              useCases={useCases}
              onSave={handleSaveSchema}
            />
          )}
        </Box>
      )}

      {canEditDomains && configSub && (
        <Box sx={{ p: 2, borderTop: "1px solid #E2E8F0" }}>
          <Button size="small" variant="outlined" color="error" onClick={() => setConfirmDelete(true)} fullWidth>
            Delete subdomain
          </Button>
        </Box>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete subdomain?"
          body={`Permanently delete "${configSub?.name.replace(/_/g, " ") ?? ""}" and all its SNOMED concepts. This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => { setConfirmDelete(false); void handleDeleteSubdomain(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      <Snackbar open={Boolean(snackMsg)} autoHideDuration={3000} onClose={() => setSnackMsg(null)} message={snackMsg} />
    </Box>
  );
}
