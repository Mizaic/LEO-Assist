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
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: total areas / NICE / platform / your-org counts.
 *   - SegmentedTabs: source filter (All / NICE / Platform / Your org).
 *   - ToolbarActions: Create area (platform admins only).
 *   - Card grid: one MetricTile-styled card per area with hover lift,
 *     framer-motion stagger, and tone accents for NICE / built-in.
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion as fm } from "framer-motion";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";

import {
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import {
  fetchDomains,
  createDomain,
  type DomainSummary,
} from "@/lib/analyticsApi";
import { useOrg } from "@/context/OrgContext";

type SourceFilter = "all" | "nice" | "platform" | "tenant";

function computeStats(domains: DomainSummary[]): StatTile[] {
  const total = domains.length;
  const nice = domains.filter((d) => d.source === "nice").length;
  const platform = domains.filter((d) => d.source === "platform").length;
  const tenant = domains.filter((d) => d.source === "tenant").length;
  return [
    {
      id: "total",
      label: "Areas",
      value: total,
      hint: "All clinical areas LEO can audit",
    },
    {
      id: "nice",
      label: "From NICE",
      value: nice,
      hint: "Sourced from NICE guidelines",
      tone: nice > 0 ? "positive" : "neutral",
    },
    {
      id: "platform",
      label: "Built-in",
      value: platform,
      hint: "Shipped with LEO",
    },
    {
      id: "tenant",
      label: "Your organisation",
      value: tenant,
      hint: "Created by your admins",
      tone: tenant > 0 ? "positive" : "neutral",
    },
  ];
}

function DomainCard({
  domain,
  onNavigate,
  index,
}: {
  domain: DomainSummary;
  onNavigate: (id: string) => void;
  index: number;
}) {
  const isNice = domain.source === "nice";
  const isPlatform = domain.source === "platform";
  const accent = isNice ? "#2563EB" : isPlatform ? "#64748B" : "#16A34A";

  return (
    <fm.button
      type="button"
      onClick={() => onNavigate(domain.id)}
      data-testid={`domain-card-${domain.id}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.22,
        ease: "easeOut",
        delay: Math.min(index, 12) * 0.04,
      }}
      whileHover={{ y: -2, boxShadow: "0 8px 18px rgba(15, 23, 42, 0.08)" }}
      whileTap={{ y: 0 }}
      style={{
        appearance: "none",
        textAlign: "left",
        background: "#FFFFFF",
        border: "1px solid #E2E8F0",
        borderRadius: 12,
        padding: 18,
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        position: "relative",
        font: "inherit",
        minHeight: 168,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: accent,
        }}
      />
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 1,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <FolderOpenOutlinedIcon sx={{ fontSize: 22, color: accent, flexShrink: 0 }} />
          <Typography
            sx={{
              fontWeight: 600,
              fontSize: "1rem",
              lineHeight: 1.25,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {domain.name}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {domain.minimum_dataset_domain ? (
            <Chip
              label="Minimum dataset"
              size="small"
              sx={{
                height: 22,
                fontSize: "0.7rem",
                bgcolor: "#EEF2FF",
                color: "#3730A3",
                border: "1px solid #C7D2FE",
                flexShrink: 0,
              }}
            />
          ) : null}
          {isNice ? (
            <Chip
              icon={<MenuBookOutlinedIcon sx={{ fontSize: 12 }} />}
              label="NICE"
              size="small"
              sx={{
                height: 22,
                fontSize: "0.7rem",
                bgcolor: "#DBEAFE",
                color: "#1E40AF",
                border: "1px solid #BFDBFE",
                flexShrink: 0,
              }}
            />
          ) : isPlatform ? (
            <Chip
              label="Built in"
              size="small"
              sx={{
                height: 22,
                fontSize: "0.7rem",
                bgcolor: "#F1F5F9",
                color: "#475569",
                border: "1px solid #E2E8F0",
                flexShrink: 0,
              }}
            />
          ) : (
            <Chip
              label="Your org"
              size="small"
              sx={{
                height: 22,
                fontSize: "0.7rem",
                bgcolor: "#ECFDF5",
                color: "#047857",
                border: "1px solid #A7F3D0",
                flexShrink: 0,
              }}
            />
          )}
        </Box>
      </Box>
      {domain.description ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            fontSize: "0.82rem",
            lineHeight: 1.45,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {domain.description}
        </Typography>
      ) : (
        <Typography
          variant="body2"
          color="text.disabled"
          sx={{ fontSize: "0.82rem", fontStyle: "italic" }}
        >
          No description yet.
        </Typography>
      )}
      <Box sx={{ flex: 1 }} />
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mt: 0.5,
        }}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontSize: "0.72rem", fontWeight: 500 }}
        >
          {domain.subdomain_count} subdomain
          {domain.subdomain_count !== 1 ? "s" : ""}
          {domain.minimum_dataset_domain
            ? ` - ${domain.minimum_dataset_subdomain_count ?? 0} minimum dataset`
            : ""}
        </Typography>
        <ChevronRightIcon sx={{ fontSize: 18, color: "#94A3B8" }} />
      </Box>
    </fm.button>
  );
}

export default function DomainsListPage() {
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

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

  useEffect(() => {
    loadDomains(sourceFilter);
  }, [loadDomains, sourceFilter]);

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreateSubmitting(true);
    try {
      const d = await createDomain(createName.trim(), createDesc.trim());
      setCreateOpen(false);
      setCreateName("");
      setCreateDesc("");
      router.push(`/settings/domains/${d.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create domain");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const showCreateButton =
    isPlatformAdmin && (sourceFilter === "all" || sourceFilter === "tenant");

  const stats = useMemo(() => computeStats(domains), [domains]);

  const niceCount = domains.filter((d) => d.source === "nice").length;
  const platformCount = domains.filter((d) => d.source === "platform").length;
  const tenantCount = domains.filter((d) => d.source === "tenant").length;
  const totalCount = domains.length;

  const toolbarActions: ToolbarAction[] = showCreateButton
    ? [
        {
          id: "create-area",
          label: "Create area",
          icon: <AddIcon fontSize="small" />,
          variant: "primary",
          onClick: () => setCreateOpen(true),
        },
      ]
    : [];

  return (
    <Box>
      <StatHero stats={stats} />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 2,
          mb: 2,
        }}
      >
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
        {toolbarActions.length > 0 ? (
          <ToolbarActions actions={toolbarActions} />
        ) : null}
      </Box>

      {!isPlatformAdmin ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          You can view areas and export code lists. Only a platform admin can
          create areas or change codes.
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
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading domains" />
        </Box>
      ) : domains.length === 0 ? (
        <Box
          sx={{
            py: 6,
            textAlign: "center",
            color: "text.secondary",
            border: "1px dashed",
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "#F8FAFC",
          }}
        >
          <Typography variant="body2">
            {sourceFilter === "nice"
              ? "No NICE areas yet. Run a guideline sync to add them."
              : isPlatformAdmin
                ? "No areas yet. Create one to get started."
                : "No areas match this filter."}
          </Typography>
        </Box>
      ) : (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(2, 1fr)",
              md: "repeat(3, 1fr)",
            },
            gap: 2,
          }}
          data-testid="domains-grid"
        >
          {domains.map((d, i) => (
            <DomainCard
              key={d.id}
              domain={d}
              index={i}
              onNavigate={(id) => router.push(`/settings/domains/${id}`)}
            />
          ))}
        </Box>
      )}

      <Dialog
        open={createOpen}
        onClose={() => !createSubmitting && setCreateOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create a new area</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Area name"
            placeholder="e.g. Cardiology Audit"
            fullWidth
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description"
            placeholder="Optional - what is this area for?"
            fullWidth
            multiline
            rows={2}
            value={createDesc}
            onChange={(e) => setCreateDesc(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCreateOpen(false)}
            disabled={createSubmitting}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleCreate}
            disabled={!createName.trim() || createSubmitting}
          >
            {createSubmitting ? "Creating..." : "Create"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
