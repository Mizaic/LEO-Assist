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
import {
  fetchDomains,
  createDomain,
  type DomainSummary,
} from "@/lib/analyticsApi";

export default function DomainsListPage() {
  const router = useRouter();
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const loadDomains = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDomains(await fetchDomains());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load domains");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDomains();
  }, [loadDomains]);

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
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Manage audit domains and their concept subdomains (SNOMED codes, terms,
        and surface forms).
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : (
        <>
          <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateOpen(true)}
            >
              Create domain
            </Button>
          </Box>

          <Grid container spacing={2}>
            {domains.map((d) => (
              <Grid key={d.id} size={{ xs: 12, sm: 6, md: 4 }}>
                <Card sx={{ height: "100%" }}>
                  <CardActionArea
                    onClick={() => router.push(`/settings/domains/${d.id}`)}
                    sx={{ height: "100%", display: "block" }}
                  >
                    <CardContent sx={{ p: 2.5 }}>
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          mb: 1.5,
                        }}
                      >
                        <FolderOpenOutlinedIcon
                          sx={{ fontSize: 36, color: "primary.main" }}
                        />
                        <ChevronRightIcon color="action" fontSize="small" />
                      </Box>
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: 600, mb: 0.5 }}
                      >
                        {d.name}
                      </Typography>
                      {d.description && (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ mb: 1 }}
                        >
                          {d.description}
                        </Typography>
                      )}
                      <Chip
                        label={`${d.subdomain_count} subdomain${d.subdomain_count !== 1 ? "s" : ""}`}
                        size="small"
                      />
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>

          {domains.length === 0 && (
            <Typography
              color="text.secondary"
              sx={{ py: 6, textAlign: "center" }}
            >
              No domains yet. Create one to get started.
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
        <DialogTitle>Create domain</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Domain name"
            placeholder="e.g. Cancer Audit"
            fullWidth
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description"
            placeholder="Optional description"
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
