"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActionArea from "@mui/material/CardActionArea";
import Grid from "@mui/material/Grid";
import Chip from "@mui/material/Chip";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import TextField from "@mui/material/TextField";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import {
  fetchDomains,
  createDomain,
  type DomainSummary,
} from "@/lib/analyticsApi";

type SourceFilter = "all" | "nice" | "platform" | "tenant";

export default function DomainsListPage() {
  const router = useRouter();
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

  const showCreateButton = sourceFilter === "all" || sourceFilter === "tenant";

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <IconButton aria-label="Back to settings" onClick={() => router.push("/settings")} size="small">
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Domain Configuration
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Manage areas and their medical codes (SNOMED terms). Each area groups
        codes that the system uses to check if a patient meets a care standard.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs
          value={sourceFilter}
          onChange={(_, v: SourceFilter) => setSourceFilter(v)}
          aria-label="Filter domains by source"
        >
          <Tab label="All" value="all" />
          <Tab label="NICE" value="nice" icon={<MenuBookOutlinedIcon fontSize="small" />} iconPosition="start" />
          <Tab label="Platform" value="platform" />
          <Tab label="Your organisation" value="tenant" />
        </Tabs>
      </Box>

      {sourceFilter === "nice" && (
        <Alert severity="info" sx={{ mb: 2 }}>
          These areas came from official NICE guidelines. You can add more codes
          to them, but you cannot delete them.
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading domains" />
        </Box>
      ) : (
        <>
          {showCreateButton && (
            <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setCreateOpen(true)}
              >
                Create area
              </Button>
            </Box>
          )}

          <Grid container spacing={2}>
            {domains.map((d) => (
              <Grid key={d.id} size={{ xs: 12, sm: 6, md: 4 }}>
                <DomainCard domain={d} onNavigate={(id) => router.push(`/settings/domains/${id}`)} />
              </Grid>
            ))}
          </Grid>

          {domains.length === 0 && (
            <Typography
              color="text.secondary"
              sx={{ py: 6, textAlign: "center" }}
            >
              {sourceFilter === "nice"
                ? "No NICE areas yet. Run a guideline sync to add them."
                : "No areas yet. Create one to get started."}
            </Typography>
          )}
        </>
      )}

      {/* Create domain dialog */}
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
            placeholder="Optional — what is this area for?"
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
            {createSubmitting ? "Creating\u2026" : "Create"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function DomainCard({
  domain,
  onNavigate,
}: {
  domain: DomainSummary;
  onNavigate: (id: string) => void;
}) {
  const isNice = domain.source === "nice";
  const isPlatform = domain.source === "platform";

  return (
    <Card sx={{ height: "100%" }}>
      <CardActionArea
        onClick={() => onNavigate(domain.id)}
        sx={{ height: "100%", display: "block" }}
      >
        <CardContent sx={{ p: 2.5 }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              mb: 1,
            }}
          >
            <FolderOpenOutlinedIcon
              sx={{ fontSize: 32, color: isNice ? "info.main" : "primary.main" }}
            />
            <ChevronRightIcon color="action" fontSize="small" />
          </Box>

          {isNice && (
            <Chip
              icon={<MenuBookOutlinedIcon />}
              label="From NICE guidelines"
              color="info"
              size="small"
              sx={{ mb: 1 }}
            />
          )}
          {isPlatform && (
            <Chip
              label="Built in"
              size="small"
              sx={{ mb: 1 }}
            />
          )}

          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 600, mb: 0.5 }}
          >
            {domain.name}
          </Typography>
          {domain.description && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mb: 1 }}
            >
              {domain.description}
            </Typography>
          )}
          <Chip
            label={`${domain.subdomain_count} subdomain${domain.subdomain_count !== 1 ? "s" : ""}`}
            size="small"
          />
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
