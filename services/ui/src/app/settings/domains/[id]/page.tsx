/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2340F614
 *   DI: DI-4885D9FF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2340F614")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";

import AddIcon from "@mui/icons-material/Add";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";

import { FilterBar, PageHero, SkeletonList } from "@leo/design-system";

import {
  fetchDomain,
  updateDomain,
  createSubdomain,
  deleteSubdomain,
  type DomainDetail,
  type SubdomainSummary,
} from "@/lib/analyticsApi";
import { useOrg } from "@/context/OrgContext";

import CreateSubdomainDialog from "../_components/CreateSubdomainDialog";
import DomainDetailChrome from "../_components/DomainDetailChrome";
import DomainSubdomainCards from "../_components/DomainSubdomainCards";
import SubdomainDetailPanel from "../_components/SubdomainDetailPanel";
import { DOMAINS_PAGE_SX } from "../_components/domainConstants";

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

  const [deleteTarget, setDeleteTarget] = useState<SubdomainSummary | null>(null);
  const [deletingSubdomain, setDeletingSubdomain] = useState<string | null>(null);

  const [selectedSubdomain, setSelectedSubdomain] = useState<string | null>(null);
  const [subFilter, setSubFilter] = useState("");

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

  useEffect(() => { loadDomain(); }, [loadDomain]);

  const handleCreateSubdomain = async () => {
    if (!createName.trim()) return;
    setCreateSubmitting(true);
    try {
      await createSubdomain(domainId, createName.trim(), { description: createDesc.trim() || undefined });
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

  const handleDeleteSubdomain = async (name: string) => {
    setDeleteTarget(null);
    setDeletingSubdomain(name);
    try {
      await deleteSubdomain(domainId, name);
      if (selectedSubdomain === name) setSelectedSubdomain(null);
      loadDomain();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete subdomain");
    } finally {
      setDeletingSubdomain(null);
    }
  };

  const filteredSubdomains = useMemo(() => {
    if (!domain) return [];
    const q = subFilter.trim().toLowerCase();
    if (!q) return domain.subdomains;
    return domain.subdomains.filter((s) =>
      s.name.toLowerCase().includes(q) || (s.description ?? "").toLowerCase().includes(q),
    );
  }, [domain, subFilter]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", ...DOMAINS_PAGE_SX }}>
      <DomainDetailChrome
        router={router}
        domainId={domainId}
        domain={domain}
        setDomain={setDomain}
        canEditDomains={canEditDomains}
        onEpisodeDetectorChange={async (val) => { await updateDomain(domainId, { episode_detector: val }); }}
        onEpisodeDetectorError={() => setError("Could not update episode detector setting.")}
      />

      {domain && (
        <PageHero
          icon={<FolderOpenOutlinedIcon />}
          title={domain.name}
          subtitle={domain.description || undefined}
          cta={canEditDomains ? { label: "Add subdomain", icon: <AddIcon />, onClick: () => setCreateOpen(true) } : undefined}
          data-testid="domain-hero"
        />
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
      )}

      <Box sx={{ display: "flex", gap: 0, alignItems: "flex-start" }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ mb: 2 }}>
            <FilterBar
              search={subFilter}
              onSearchChange={setSubFilter}
              searchPlaceholder="Search subdomains"
              aria-label="Search subdomains"
            />
          </Box>

          {loading ? (
            <SkeletonList rows={4} itemHeight={80} data-testid="subdomains-skeleton" />
          ) : domain ? (
            <DomainSubdomainCards
              subdomainCount={filteredSubdomains.length}
              subdomains={filteredSubdomains}
              canEditDomains={canEditDomains}
              deletingSubdomain={deletingSubdomain}
              onCreateClick={() => setCreateOpen(true)}
              onConfigure={(sub) => setSelectedSubdomain(sub.name)}
              onDelete={setDeleteTarget}
            />
          ) : null}
        </Box>

        {selectedSubdomain && (
          <SubdomainDetailPanel
            domainId={domainId}
            subdomainName={selectedSubdomain}
            canEditDomains={canEditDomains}
            onClose={() => setSelectedSubdomain(null)}
            onDeleted={() => { setSelectedSubdomain(null); loadDomain(); }}
          />
        )}
      </Box>

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

      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete subdomain?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Permanently delete <strong>{deleteTarget?.name.replace(/_/g, " ")}</strong>
            {" "}and all its SNOMED concepts. This cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => deleteTarget && void handleDeleteSubdomain(deleteTarget.name)}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
