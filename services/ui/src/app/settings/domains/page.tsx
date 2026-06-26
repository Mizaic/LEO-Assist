/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   Also implements: DO-DA9FD5E8
 *   DI: DI-340279C1, DI-6424B6FC
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CFA1ED55")
 */
"use client";

/**
 * Domains -- Wave E Phase 3c redesign
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145.
 *
 * DomainCard is defined in ./_components/DomainCard.tsx and imported
 * below. It uses framer-motion for entrance animations:
 *   import { motion as fm } from "framer-motion";
 *   function DomainCard({ domain, onEdit, onDelete }: DomainCardProps) { ... }
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import AddIcon from "@mui/icons-material/Add";

import {
  FilterBar,
  SegmentedTabs,
  SkeletonList,
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import {
  fetchDomains,
  createDomain,
  updateDomain,
  deleteDomain,
  type DomainSummary,
} from "@/lib/analyticsApi";
import { useOrg } from "@/context/OrgContext";
import ConfirmDialog from "@/components/ConfirmDialog";
import DomainCard from "./_components/DomainCard";

type SourceFilter = "all" | "nice" | "platform" | "tenant";

function computeStats(domains: DomainSummary[]): StatTile[] {
  return [
    { id: "total", label: "Areas", value: domains.length, hint: "All clinical areas LEO can audit" },
    { id: "nice", label: "From NICE", value: domains.filter((d) => d.source === "nice").length, hint: "Sourced from NICE guidelines", tone: domains.filter((d) => d.source === "nice").length > 0 ? "positive" : "neutral" },
    { id: "platform", label: "Built-in", value: domains.filter((d) => d.source === "platform").length, hint: "Shipped with LEO" },
    { id: "tenant", label: "Your organisation", value: domains.filter((d) => d.source === "tenant").length, hint: "Created by your admins", tone: domains.filter((d) => d.source === "tenant").length > 0 ? "positive" : "neutral" },
  ];
}

export default function DomainsListPage() {
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const [editTarget, setEditTarget] = useState<DomainSummary | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<DomainSummary | null>(null);
  const [snackMsg, setSnackMsg] = useState<string | null>(null);

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
  }, []);

  useEffect(() => { loadDomains(sourceFilter); }, [loadDomains, sourceFilter]);

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreateSubmitting(true);
    try {
      const d = await createDomain(createName.trim(), createDesc.trim());
      setCreateOpen(false);
      setCreateName("");
      setCreateDesc("");
      setSnackMsg("Domain created");
      router.push(`/settings/domains/${d.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create domain");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleEdit = async () => {
    if (!editTarget || !editName.trim()) return;
    setEditSubmitting(true);
    try {
      await updateDomain(editTarget.id, { name: editName.trim(), description: editDesc.trim() });
      setEditTarget(null);
      await loadDomains(sourceFilter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update domain");
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteDomain(target.id);
      setSnackMsg("Domain deleted");
      await loadDomains(sourceFilter);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete domain");
    }
  };

  const openEdit = (domain: DomainSummary) => {
    setEditTarget(domain);
    setEditName(domain.name);
    setEditDesc(domain.description ?? "");
  };

  const showCreateButton = isPlatformAdmin && (sourceFilter === "all" || sourceFilter === "tenant");
  const stats = useMemo(() => computeStats(domains), [domains]);

  const niceCount = domains.filter((d) => d.source === "nice").length;
  const platformCount = domains.filter((d) => d.source === "platform").length;
  const tenantCount = domains.filter((d) => d.source === "tenant").length;
  const totalCount = domains.length;

  const toolbarActions: ToolbarAction[] = showCreateButton
    ? [{ id: "create-area", label: "Create area", icon: <AddIcon fontSize="small" />, variant: "primary", onClick: () => setCreateOpen(true) }]
    : [];

  const filtered = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return domains;
    return domains.filter((d) =>
      d.name.toLowerCase().includes(q) || (d.description ?? "").toLowerCase().includes(q),
    );
  }, [domains, searchText]);

  return (
    <Box>
      <StatHero stats={stats} />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
      ) : null}

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 2, mb: 2 }}>
        <SegmentedTabs
          tabs={[
            { id: "all", label: "All", count: totalCount },
            { id: "nice", label: "NICE", count: niceCount },
            { id: "platform", label: "Built-in", count: platformCount },
            { id: "tenant", label: "Your organisation", count: tenantCount },
          ]}
          value={sourceFilter}
          onChange={(id) => setSourceFilter(id as SourceFilter)}
          aria-label="Filter areas by source"
        />
        {toolbarActions.length > 0 ? <ToolbarActions actions={toolbarActions} /> : null}
      </Box>

      <FilterBar
        search={searchText}
        onSearchChange={setSearchText}
        searchPlaceholder="Search areas by name or description"
        aria-label="Search clinical areas"
      />

      {!isPlatformAdmin ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          You can view areas and export code lists. Only a platform admin can create areas or change codes.
        </Alert>
      ) : null}

      {sourceFilter === "nice" ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {isPlatformAdmin
            ? "These areas came from official NICE guidelines. You can add more codes to them, but you cannot delete them."
            : "These areas came from official NICE guidelines. You can view them and export code lists. Only a platform admin can add or change codes."}
        </Alert>
      ) : null}

      {loading ? (
        <SkeletonList rows={3} itemHeight={168} gap={16} data-testid="domains-skeleton" />
      ) : domains.length === 0 ? (
        <Box sx={{ py: 6, textAlign: "center", color: "text.secondary", border: "1px dashed", borderColor: "divider", borderRadius: 2, bgcolor: "#F8FAFC" }}>
          <Box component="p" sx={{ m: 0, fontSize: "0.875rem" }}>
            {sourceFilter === "nice"
              ? "No NICE areas yet. Run a guideline sync to add them."
              : isPlatformAdmin
                ? "No areas yet. Create one to get started."
                : "No areas match this filter."}
          </Box>
        </Box>
      ) : filtered.length === 0 ? (
        <Alert severity="info">No areas match your search.</Alert>
      ) : (
        <Box
          sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(3, 1fr)" }, gap: 2 }}
          data-testid="domains-grid"
        >
          {filtered.map((d, i) => (
            <DomainCard
              key={d.id}
              domain={d}
              index={i}
              canEdit={isPlatformAdmin}
              onNavigate={(id) => router.push(`/settings/domains/${id}`)}
              onEdit={openEdit}
              onDelete={setDeleteTarget}
            />
          ))}
        </Box>
      )}

      <Dialog open={createOpen} onClose={() => !createSubmitting && setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create a new area</DialogTitle>
        <DialogContent>
          <TextField autoFocus margin="dense" label="Area name" placeholder="e.g. Cardiology Audit" fullWidth value={createName} onChange={(e) => setCreateName(e.target.value)} />
          <TextField margin="dense" label="Description" placeholder="Optional - what is this area for?" fullWidth multiline rows={2} value={createDesc} onChange={(e) => setCreateDesc(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={createSubmitting}>Cancel</Button>
          <Button variant="contained" onClick={() => void handleCreate()} disabled={!createName.trim() || createSubmitting}>
            {createSubmitting ? "Creating..." : "Create"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(editTarget)} onClose={() => !editSubmitting && setEditTarget(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Rename area</DialogTitle>
        <DialogContent>
          <TextField autoFocus margin="dense" label="Area name" fullWidth value={editName} onChange={(e) => setEditName(e.target.value)} />
          <TextField margin="dense" label="Description" fullWidth multiline rows={2} value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditTarget(null)} disabled={editSubmitting}>Cancel</Button>
          <Button variant="contained" onClick={() => void handleEdit()} disabled={!editName.trim() || editSubmitting}>
            {editSubmitting ? "Saving..." : "Save"}
          </Button>
        </DialogActions>
      </Dialog>

      {deleteTarget ? (
        <ConfirmDialog
          title="Delete area?"
          body={`Permanently delete "${deleteTarget.name}" and all its subdomains. This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => void handleDelete()}
          onCancel={() => setDeleteTarget(null)}
        />
      ) : null}

      <Snackbar
        open={Boolean(snackMsg)}
        autoHideDuration={3000}
        onClose={() => setSnackMsg(null)}
        message={snackMsg}
      />
    </Box>
  );
}
