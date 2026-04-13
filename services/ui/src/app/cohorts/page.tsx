"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import DeleteIcon from "@mui/icons-material/Delete";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import AddIcon from "@mui/icons-material/Add";
import {
  type Cohort,
  type CohortFilter,
  fetchCohorts,
  createCohort,
  resolveCohort,
  deleteCohort,
} from "@/lib/analyticsApi";
import { sortByIsoDateDesc } from "@/lib/dateSort";

const EPISODE_STATUS_OPTIONS = [
  "building",
  "confirmed",
  "excluded",
  "inconclusive",
  "merged",
  "pending",
];

export default function CohortsPage() {
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [orgId, setOrgId] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [episodeStatus, setEpisodeStatus] = useState<string[]>([]);
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");

  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const cohortsSorted = useMemo(
    () => sortByIsoDateDesc(cohorts, (c) => c.created_at),
    [cohorts],
  );

  const loadCohorts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCohorts();
      setCohorts(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCohorts();
  }, [loadCohorts]);

  const buildFilters = (): CohortFilter => ({
    ...(orgId && { org_id: orgId }),
    ...(dateStart && { date_range_start: dateStart }),
    ...(dateEnd && { date_range_end: dateEnd }),
    ...(episodeStatus.length > 0 && { episode_status: episodeStatus }),
    ...(ageMin && { age_min: parseInt(ageMin, 10) }),
    ...(ageMax && { age_max: parseInt(ageMax, 10) }),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      await createCohort(name, description, buildFilters());
      setDialogOpen(false);
      resetForm();
      loadCohorts();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (cohortId: string) => {
    try {
      await deleteCohort(cohortId);
      loadCohorts();
    } catch (err) {
      setError(String(err));
    }
  };

  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleRunDetection = async (cohortId: string) => {
    try {
      const patients = await resolveCohort(cohortId);
      const base = window.location.origin;
      const res = await fetch(`${base}/api/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cohort_id: cohortId }),
      });
      if (!res.ok) throw new Error(`Pipeline run failed (${res.status} ${res.statusText})`);
      setSuccessMsg(`Episode detection started for ${patients.total} patients`);
    } catch (err) {
      setError(String(err));
    }
  };

  const resetForm = () => {
    setName("");
    setDescription("");
    setOrgId("");
    setDateStart("");
    setDateEnd("");
    setEpisodeStatus([]);
    setAgeMin("");
    setAgeMax("");
    setPreviewCount(null);
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: "auto" }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 3,
        }}
      >
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
          Cohort Builder
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setDialogOpen(true)}
        >
          New Cohort
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {successMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccessMsg(null)}>
          {successMsg}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} variant="rounded" height={100} />
          ))}
        </Box>
      ) : cohorts.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: "center", py: 6 }}>
            <Typography variant="body1" color="text.secondary">
              No cohorts created yet. Create your first cohort to start
              selecting patients for episode detection.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {cohortsSorted.map((c) => (
            <Card key={c.cohort_id}>
              <CardContent>
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                      {c.name}
                    </Typography>
                    {c.description && (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mb: 1 }}
                      >
                        {c.description}
                      </Typography>
                    )}
                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                      <Chip
                        label={`${c.patient_count} patients`}
                        size="small"
                        color="primary"
                      />
                      {c.filters?.org_id && (
                        <Chip
                          label={`Org: ${c.filters.org_id}`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                      {c.filters?.episode_status && (
                        <Chip
                          label={`Status: ${(c.filters.episode_status as string[]).join(", ")}`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                      {c.created_at && (
                        <Chip
                          label={`Created: ${c.created_at.slice(0, 10)}`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                    </Box>
                  </Box>
                  <Box sx={{ display: "flex", gap: 1 }}>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<PlayArrowIcon />}
                      onClick={() => handleRunDetection(c.cohort_id)}
                    >
                      Run Detection
                    </Button>
                    <IconButton
                      aria-label="Delete cohort"
                      size="small"
                      color="error"
                      onClick={() => handleDelete(c.cohort_id)}
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create New Cohort</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <TextField
              label="Cohort Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              fullWidth
            />
            <TextField
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              multiline
              rows={2}
              fullWidth
            />
            <TextField
              label="Organisation ID"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              fullWidth
              placeholder="e.g. ORG_12345"
            />
            <Box sx={{ display: "flex", gap: 2 }}>
              <TextField
                label="Date from"
                type="date"
                value={dateStart}
                onChange={(e) => setDateStart(e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label="Date to"
                type="date"
                value={dateEnd}
                onChange={(e) => setDateEnd(e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
            </Box>
            <FormControl fullWidth>
              <InputLabel>Episode Status</InputLabel>
              <Select
                multiple
                value={episodeStatus}
                onChange={(e) => setEpisodeStatus(e.target.value as string[])}
                label="Episode Status"
                renderValue={(sel) => (
                  <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                    {(sel as string[]).map((v) => (
                      <Chip key={v} label={v} size="small" />
                    ))}
                  </Box>
                )}
              >
                {EPISODE_STATUS_OPTIONS.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ display: "flex", gap: 2 }}>
              <TextField
                label="Min Age"
                type="number"
                value={ageMin}
                onChange={(e) => setAgeMin(e.target.value)}
                fullWidth
              />
              <TextField
                label="Max Age"
                type="number"
                value={ageMax}
                onChange={(e) => setAgeMax(e.target.value)}
                fullWidth
              />
            </Box>
            {previewCount !== null && (
              <Alert severity="info">
                {previewCount} patients match these filters
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={!name || saving}
          >
            {saving ? "Saving..." : "Save Cohort"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
