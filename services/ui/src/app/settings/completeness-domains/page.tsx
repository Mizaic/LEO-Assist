/**
 * Completeness Domains -- admin view of ServiceDomain completeness schemas.
 *
 * Lists all tenant AuditDomain nodes that carry a completeness_schema.
 * Each domain shows the groups written by the last FormSchema save.
 * Admins can edit groups inline using FormSchemaCompletenessEditor.
 *
 * Atlas trace:
 *   UN: UN-3B25A20E
 *   DI: DI-26546721
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckIcon from "@mui/icons-material/Check";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  StatHero,
  type StatTile,
} from "@leo/design-system";
import { FormSchemaCompletenessEditor } from "@/components/operations/FormSchemaCompletenessEditor";
import type { CompletenessLogicGroup } from "@/components/operations/formSchemaTeach";

interface DomainSummary {
  domain_id: string;
  domain_name: string;
  organization_id: string;
  organization_name: string;
  service_id: string;
  service_name: string;
  completeness_groups: CompletenessLogicGroup[];
  updated_at: string;
  updated_by: string;
}

async function fetchDomains(): Promise<DomainSummary[]> {
  const res = await fetch("/api/completeness-domains/");
  if (!res.ok) throw new Error("Could not load completeness domains. Please retry.");
  const data = await res.json();
  return data.domains ?? [];
}

async function saveDomain(
  domain: DomainSummary,
  groups: CompletenessLogicGroup[]
): Promise<void> {
  const res = await fetch(`/api/completeness-domains/${domain.domain_id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      form_name: domain.domain_name,
      organization_id: domain.organization_id,
      service_id: domain.service_id,
      completeness_groups: groups,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Could not save. Please retry.");
  }
}

interface DomainCardProps {
  domain: DomainSummary;
  index: number;
}

function DomainCard({ domain, index }: DomainCardProps) {
  const [open, setOpen] = useState(false);
  const [groups, setGroups] = useState<CompletenessLogicGroup[]>(
    domain.completeness_groups as CompletenessLogicGroup[]
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await saveDomain(domain, groups);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [domain, groups]);

  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: 12,
        border: "1px solid",
        borderColor: "divider",
        p: "18px",
        minHeight: 80,
        transition: "box-shadow 0.18s ease",
        "&:hover": { boxShadow: "0 2px 12px rgba(0,0,0,0.07)" },
      }}
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
      data-testid="completeness-domain-card"
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
          background: "#0d46d6",
        }}
      />
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {domain.domain_name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {domain.service_id || domain.organization_name || domain.domain_id}
          </Typography>
          {domain.updated_by && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Last saved by {domain.updated_by}
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Chip
            label={`${domain.completeness_groups.length} group${domain.completeness_groups.length === 1 ? "" : "s"}`}
            size="small"
            color="primary"
            variant="outlined"
          />
          <Button
            size="small"
            endIcon={<ExpandMoreIcon sx={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.18s" }} />}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Collapse editor" : "Edit groups"}
          >
            {open ? "Collapse" : "Edit groups"}
          </Button>
        </Box>
      </Box>

      <Collapse in={open} timeout="auto">
        <Box sx={{ mt: 2 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }}>
              {error}
            </Alert>
          )}
          {saved && (
            <Alert severity="success" sx={{ mb: 1 }} icon={<CheckIcon fontSize="inherit" />}>
              Completeness groups saved.
            </Alert>
          )}
          <FormSchemaCompletenessEditor
            groups={groups}
            onChange={setGroups}
          />
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button
              variant="contained"
              size="small"
              onClick={handleSave}
              disabled={saving}
              startIcon={saving ? <CircularProgress size={14} aria-label="Saving" role="status" /> : undefined}
            >
              {saving ? "Saving..." : "Save changes"}
            </Button>
            <Button size="small" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </Stack>
        </Box>
      </Collapse>
    </Box>
  );
}

export default function CompletenessDomainsPage() {
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchDomains()
      .then(setDomains)
      .catch((err) => setError(err.message ?? "Could not load completeness domains."))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => {
    if (!search.trim()) return domains;
    const q = search.toLowerCase();
    return domains.filter(
      (d) =>
        d.domain_name.toLowerCase().includes(q) ||
        d.service_id.toLowerCase().includes(q) ||
        d.organization_name.toLowerCase().includes(q)
    );
  }, [domains, search]);

  const stats: StatTile[] = useMemo(
    () => [
      {
        id: "domains",
        label: "Domains",
        value: domains.length,
        hint: "All service domains with a completeness schema",
      },
      {
        id: "with-rules",
        label: "With rules",
        value: domains.filter((d) => d.completeness_groups.length > 0).length,
        hint: "Domains that already have minimum-dataset groups",
        tone: "positive",
      },
    ],
    [domains]
  );

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Completeness domains
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Each domain holds the minimum dataset rules for a service. Rules are
        written here when you save a form schema, and are read by the pipeline
        quality check.
      </Typography>

      <StatHero stats={stats} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <TextField
        size="small"
        placeholder="Search domains..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: 320 }}
        inputProps={{ "aria-label": "Search completeness domains" }}
      />

      {loading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "text.secondary" }}>
          <CircularProgress size={18} aria-label="Loading" role="status" />
          <Typography variant="body2">Loading domains...</Typography>
        </Box>
      )}

      {!loading && !error && domains.length === 0 && (
        <Alert severity="info">
          No completeness domains yet. Save a form schema with an organisation
          and service to create one.
        </Alert>
      )}

      {!loading && !error && domains.length > 0 && visible.length === 0 && (
        <Alert severity="info">No domains match this search.</Alert>
      )}

      <Stack spacing={1.5}>
        {visible.map((domain, idx) => (
          <DomainCard key={domain.domain_id} domain={domain} index={idx} />
        ))}
      </Stack>
    </Box>
  );
}
