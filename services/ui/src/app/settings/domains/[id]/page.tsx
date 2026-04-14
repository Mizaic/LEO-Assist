"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import {
  fetchDomain,
  updateDomain,
  createSubdomain,
  deleteSubdomain,
  fetchSubdomain,
  updateSubdomain,
  addConceptToSubdomain,
  removeConceptFromSubdomain,
  exportSubdomain,
  type DomainDetail,
  type SubdomainSummary,
  type SubdomainDetail,
} from "@/lib/analyticsApi";
import { searchTerms, fetchSemanticTags, fetchDescendants } from "@/lib/api";
import { useOrg } from "@/context/OrgContext";
import CreateSubdomainDialog from "../_components/CreateSubdomainDialog";
import ConfigureSubdomainDialog from "../_components/ConfigureSubdomainDialog";
import DomainDetailChrome from "../_components/DomainDetailChrome";
import DomainSubdomainCards from "../_components/DomainSubdomainCards";

export default function DomainDetailPage() {
  const params = useParams();
  const domainId = params.id as string;
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();
  const canEditDomains = isPlatformAdmin;

  const [domain, setDomain] = useState<DomainDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const [configSub, setConfigSub] = useState<SubdomainDetail | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [configSubmitting, setConfigSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<
    Array<{ snomed_concept_id: string; term: string; semantic_tag?: string }>
  >([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const [descendantPreview, setDescendantPreview] = useState<{
    parentId: string;
    parentTerm: string;
    results: Array<{
      snomed_concept_id: string;
      term: string;
      semantic_tag?: string;
      surface_form_count: number;
      surface_forms: string[];
    }>;
  } | null>(null);
  const [descendantLoading, setDescendantLoading] = useState<string | null>(null);
  const [descendantListOpen, setDescendantListOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState<"concepts" | "expanded" | null>(
    null,
  );

  const [pendingConcept, setPendingConcept] = useState<{
    conceptId: number;
    term: string;
  } | null>(null);
  const [addBenchmarkKey, setAddBenchmarkKey] = useState("");

  const [allSemanticTags, setAllSemanticTags] = useState<string[]>([]);

  const [deleteTarget, setDeleteTarget] = useState<SubdomainSummary | null>(null);
  const [deletingSubdomain, setDeletingSubdomain] = useState<string | null>(null);

  useEffect(() => {
    fetchSemanticTags()
      .then(setAllSemanticTags)
      .catch(() => {});
  }, []);

  const loadDomain = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDomain(await fetchDomain(domainId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load domain");
    } finally {
      setLoading(false);
    }
  }, [domainId]);

  useEffect(() => {
    loadDomain();
  }, [loadDomain]);

  const activeTags = configSub?.semantic_tags ?? [];

  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const tags = activeTags.length > 0 ? activeTags : undefined;
      setSearchResults(await searchTerms(q, 15, tags));
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery, activeTags]);

  useEffect(() => {
    const t = setTimeout(handleSearch, 300);
    return () => clearTimeout(t);
  }, [searchQuery, handleSearch]);

  const handleCreateSubdomain = async () => {
    if (!createName.trim()) return;
    setCreateSubmitting(true);
    try {
      await createSubdomain(domainId, createName.trim(), {
        description: createDesc.trim() || undefined,
      });
      setCreateOpen(false);
      setCreateName("");
      setCreateDesc("");
      loadDomain();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create subdomain");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleDeleteSubdomain = async () => {
    if (!deleteTarget) return;
    setDeletingSubdomain(deleteTarget.name);
    setDeleteTarget(null);
    try {
      await deleteSubdomain(domainId, deleteTarget.name);
      loadDomain();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete subdomain");
    } finally {
      setDeletingSubdomain(null);
    }
  };

  const openConfig = async (sub: SubdomainSummary) => {
    setConfigSub(null);
    setConfigOpen(true);
    setSearchQuery("");
    setSearchResults([]);
    setDescendantPreview(null);
    setDescendantLoading(null);
    setDescendantListOpen(false);
    setPendingConcept(null);
    setAddBenchmarkKey("");
    try {
      setConfigSub(await fetchSubdomain(domainId, sub.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load subdomain");
      setConfigOpen(false);
    }
  };

  const handleAddConcept = async (
    conceptId: number,
    term: string,
    benchmarkKey?: string,
  ) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      const updated = await addConceptToSubdomain(
        domainId,
        configSub.name,
        conceptId,
        term,
        [],
        benchmarkKey || undefined,
      );
      setConfigSub(updated);
      setSearchQuery("");
      setSearchResults([]);
      setPendingConcept(null);
      setAddBenchmarkKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleRemoveConcept = async (conceptId: number) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      setConfigSub(
        await removeConceptFromSubdomain(domainId, configSub.name, conceptId),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleUpdateSubdomain = async (updates: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
    assertion_filter?: string[];
    constructs?: Array<{
      id: string;
      display_name: string;
      description?: string;
      logic: "ALL" | "ANY";
      roles: Array<{ role: string; concept_ids: number[]; required: boolean }>;
    }>;
  }) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      const updated = await updateSubdomain(domainId, configSub.name, updates);
      setConfigSub((prev) =>
        prev ? { ...prev, ...updated, concepts: prev.concepts } : null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update subdomain");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleFetchDescendants = async (conceptId: string, term: string) => {
    if (!configSub) return;
    setDescendantLoading(conceptId);
    setDescendantPreview(null);
    try {
      const tags = activeTags.length > 0 ? activeTags : undefined;
      const results = await fetchDescendants(conceptId, 3, tags);
      setDescendantPreview({ parentId: conceptId, parentTerm: term, results });
    } catch {
      setError("Failed to fetch descendants");
    } finally {
      setDescendantLoading(null);
    }
  };

  const handleConfirmDescendants = async () => {
    if (!configSub || !descendantPreview) return;
    setConfigSubmitting(true);
    try {
      const updated = await addConceptToSubdomain(
        domainId,
        configSub.name,
        parseInt(descendantPreview.parentId, 10),
        descendantPreview.parentTerm,
        [],
        addBenchmarkKey || undefined,
      );
      setConfigSub(updated);
      setDescendantPreview(null);
      setDescendantListOpen(false);
      setSearchQuery("");
      setSearchResults([]);
      setAddBenchmarkKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleExport = async (includeChildren: boolean) => {
    if (!configSub) return;
    setExportLoading(includeChildren ? "expanded" : "concepts");
    try {
      const data = await exportSubdomain(domainId, configSub.name, includeChildren);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = includeChildren
        ? `${configSub.name}-expanded.json`
        : `${configSub.name}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(null);
    }
  };

  const existingConceptIds = new Set(
    configSub?.concepts.map((c) => c.concept_id) ?? [],
  );

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <DomainDetailChrome
        router={router}
        domainId={domainId}
        domain={domain}
        setDomain={setDomain}
        canEditDomains={canEditDomains}
        onEpisodeDetectorChange={async (val) => {
          await updateDomain(domainId, { episode_detector: val });
        }}
        onEpisodeDetectorError={() =>
          setError("Could not update episode detector setting.")
        }
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : domain ? (
        <DomainSubdomainCards
          subdomainCount={domain.subdomains.length}
          subdomains={domain.subdomains}
          canEditDomains={canEditDomains}
          deletingSubdomain={deletingSubdomain}
          onCreateClick={() => setCreateOpen(true)}
          onConfigure={openConfig}
          onDelete={setDeleteTarget}
        />
      ) : null}

      <CreateSubdomainDialog
        open={createOpen}
        createSubmitting={createSubmitting}
        createName={createName}
        createDesc={createDesc}
        onClose={() => setCreateOpen(false)}
        onCreateNameChange={setCreateName}
        onCreateDescChange={setCreateDesc}
        onSubmit={handleCreateSubdomain}
      />

      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Delete subdomain?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Permanently delete <strong>{deleteTarget?.name.replace(/_/g, " ")}</strong>
            {" "}and all its SNOMED concepts. This cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => void handleDeleteSubdomain()}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      <ConfigureSubdomainDialog
        open={configOpen}
        configSubmitting={configSubmitting}
        configSub={configSub}
        setConfigSub={setConfigSub}
        canEditDomains={canEditDomains}
        allSemanticTags={allSemanticTags}
        onUpdateSubdomain={handleUpdateSubdomain}
        onClearSearchResults={() => setSearchResults([])}
        onDismiss={() => setConfigOpen(false)}
        onCloseButton={() => {
          setConfigOpen(false);
          loadDomain();
        }}
        onRemoveConcept={handleRemoveConcept}
        exportLoading={exportLoading}
        onExport={handleExport}
        searchPanelProps={{
          activeTags,
          searchQuery,
          onSearchQueryChange: setSearchQuery,
          searchResults,
          searchLoading,
          configSubmitting,
          existingConceptIds,
          descendantPreview,
          descendantLoading,
          descendantListOpen,
          onToggleDescendantList: () => setDescendantListOpen((o) => !o),
          pendingConcept,
          addBenchmarkKey,
          onAddBenchmarkKeyChange: setAddBenchmarkKey,
          onStartAddConcept: (conceptId: number, term: string) => {
            setPendingConcept({ conceptId, term });
            setAddBenchmarkKey("");
            setDescendantPreview(null);
          },
          onCancelPending: () => {
            setPendingConcept(null);
            setAddBenchmarkKey("");
          },
          onFetchDescendants: handleFetchDescendants,
          onClearDescendantPreview: () => {
            setDescendantPreview(null);
            setDescendantListOpen(false);
          },
          onConfirmAddConcept: handleAddConcept,
          onConfirmDescendants: handleConfirmDescendants,
        }}
      />
    </Box>
  );
}
