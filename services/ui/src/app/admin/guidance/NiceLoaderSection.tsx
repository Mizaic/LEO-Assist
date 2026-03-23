"use client";

import { useCallback, useEffect, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Stack from "@mui/material/Stack";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import TaxonomyBrowserDrawer from "./TaxonomyBrowserDrawer";


interface GuidelineOption {
  code: string;
  title: string;
  type: string;
}

interface Job {
  job_id: string;
  code: string;
  status: string;
  step?: string;
  completed_at?: string | null;
  recommendation_count?: number;
}

/** NICE code pattern: NG12, CG89, TA123, QS42, DG3, IPG4, etc. */
const NICE_CODE_RE = /^(NG|CG|TA|DG|IPG|QS|PH|SC|MTG|LGB|HSG|MPG|ES)\d+$/i;

function isNiceCode(value: string): boolean {
  return NICE_CODE_RE.test(value.trim());
}

interface Props {
  onGuidelineLoaded?: () => void;
}

export default function NiceLoaderSection({ onGuidelineLoaded }: Props) {
  const [options, setOptions] = useState<GuidelineOption[]>([]);
  const [selected, setSelected] = useState<GuidelineOption | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ingestLog, setIngestLog] = useState<string[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [refreshJobs, setRefreshJobs] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      if (inputValue.length < 2) {
        setOptions([]);
        return;
      }
      setSearchError(null);
      fetch(`/api/nice/catalogue?q=${encodeURIComponent(inputValue)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
        .then(setOptions)
        .catch(() => setSearchError("Could not search for guidelines. Try again."));
    }, 300);
    return () => clearTimeout(t);
  }, [inputValue]);

  useEffect(() => {
    fetch("/api/nice/jobs")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setJobs)
      .catch(() => setJobsError("Could not load recent jobs."));
  }, [refreshJobs]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const resp = await fetch("/api/nice/catalogue/sync", { method: "POST" });
      if (!resp.ok) throw new Error(await resp.text());
      const { job_id } = await resp.json();
      // Poll for completion
      const poll = setInterval(async () => {
        const s = await fetch(`/api/nice/jobs/${job_id}/status`).then((r) => r.json()).catch(() => null);
        if (s?.status === "done") {
          setSyncMessage(`Catalogue updated. ${s.catalogue_count ?? 0} guidelines now available to search.`);
          setSyncing(false);
          clearInterval(poll);
        } else if (s?.status === "error") {
          setSyncMessage("Sync failed. Check the API key and try again.");
          setSyncing(false);
          clearInterval(poll);
        }
      }, 3000);
    } catch {
      setSyncMessage("Could not start sync. Please try again.");
      setSyncing(false);
    }
  }, []);

  /** Called when user clicks Load inside the taxonomy drawer. */
  const handleBrowseSelect = useCallback(
    (code: string) => {
      setBrowseOpen(false);
      setInputValue(code);
      setSelected(null);
    },
    [],
  );

  const handleIngest = useCallback(async () => {
    if (!selected && !inputValue.trim()) return;
    const code = selected?.code || inputValue.trim().toUpperCase();
    setLoading(true);
    setIngestLog([`Starting: loading guideline ${code}...`]);

    try {
      const resp = await fetch("/api/nice/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const { job_id } = await resp.json();

      const es = new EventSource(`/api/nice/events?job_id=${job_id}`);
      es.addEventListener("progress", (e) => {
        const d = JSON.parse(e.data);
        setIngestLog((prev) => [...prev, d.step]);
      });
      es.addEventListener("done", (e) => {
        const d = JSON.parse(e.data);
        setIngestLog((prev) => [...prev, `Done. Loaded ${d.recommendation_count ?? 0} recommendations.`]);
        es.close();
        setLoading(false);
        setRefreshJobs((n) => n + 1);
        onGuidelineLoaded?.();
      });
      es.addEventListener("error", () => {
        setIngestLog((prev) => [...prev, "Something went wrong. Please try again."]);
        es.close();
        setLoading(false);
        setRefreshJobs((n) => n + 1);
      });
    } catch (err) {
      setIngestLog((prev) => [...prev, `Error: ${String(err)}`]);
      setLoading(false);
    }
  }, [selected, inputValue, onGuidelineLoaded]);

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Type a condition name to find a guideline, then click
        {" "}<strong>Load this guideline</strong>. You can also type a NICE
        code directly (for example, NG151).
      </Typography>

      {/* Catalogue sync + taxonomy browser */}
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 2 }}>
        <Button
          size="small"
          variant="outlined"
          disabled={syncing}
          onClick={handleSync}
          aria-label="Refresh the guideline search list from NICE"
        >
          {syncing ? "Refreshing list…" : "Refresh guideline list"}
        </Button>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AccountTreeOutlinedIcon />}
          onClick={() => setBrowseOpen(true)}
          aria-label="Browse guidelines by clinical area"
        >
          Browse by area
        </Button>
        <Typography variant="caption" color="text.secondary">
          Run &lsquo;Refresh&rsquo; once to make all NICE guidelines searchable by name, or browse by clinical area.
        </Typography>
      </Stack>
      {syncMessage && (
        <Alert
          severity={syncMessage.includes("failed") || syncMessage.includes("Could not") ? "error" : "success"}
          sx={{ mb: 2 }}
          onClose={() => setSyncMessage(null)}
        >
          {syncMessage}
        </Alert>
      )}

      {searchError && <Alert severity="error" sx={{ mb: 2 }}>{searchError}</Alert>}

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 2 }}>
        <Autocomplete
          sx={{ flex: 1 }}
          options={options}
          getOptionLabel={(o) =>
            typeof o === "string" ? o : `${o.code} -- ${o.title}`
          }
          value={selected}
          inputValue={inputValue}
          onInputChange={(_, v) => setInputValue(v)}
          onChange={(_, v) =>
            setSelected(typeof v === "string" ? null : v)
          }
          freeSolo
          renderInput={(params) => (
            <TextField
              {...params}
              label="Search for a guideline"
              placeholder="e.g. bowel cancer or NG151"
              size="small"
              helperText={
                inputValue && !selected && !isNiceCode(inputValue)
                  ? "Pick a guideline from the list, or type a code like NG151"
                  : undefined
              }
              inputProps={{ ...params.inputProps, "aria-label": "Search for a NICE guideline" }}
            />
          )}
          renderOption={(props, o) => (
            <li {...props} key={o.code}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip label={o.code} size="small" color="primary" variant="outlined" />
                <Typography variant="body2">{o.title}</Typography>
              </Stack>
            </li>
          )}
        />
        <Button
          variant="contained"
          disabled={loading || (!selected && !isNiceCode(inputValue))}
          onClick={handleIngest}
          aria-label="Load this guideline"
        >
          Load this guideline
        </Button>
      </Stack>

      {loading && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress sx={{ mb: 1 }} />
          <Box
            sx={{
              maxHeight: 120,
              overflowY: "auto",
              bgcolor: "grey.50",
              p: 1,
              borderRadius: 1,
              fontFamily: "monospace",
              fontSize: "0.75rem",
            }}
          >
            {ingestLog.map((line, i) => (
              <Box key={i}>{line}</Box>
            ))}
          </Box>
        </Box>
      )}

      {!loading && ingestLog.length > 0 && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {ingestLog[ingestLog.length - 1]}
        </Alert>
      )}

      {jobsError && <Alert severity="error" sx={{ mb: 2 }}>{jobsError}</Alert>}

      {jobs.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            Recent loads
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Recommendations</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.job_id}>
                  <TableCell><strong>{j.code}</strong></TableCell>
                  <TableCell>
                    <Chip
                      label={j.status}
                      size="small"
                      color={j.status === "done" ? "success" : j.status === "error" ? "error" : "default"}
                    />
                  </TableCell>
                  <TableCell>{j.recommendation_count ?? "--"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}

      <TaxonomyBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onSelectGuideline={handleBrowseSelect}
      />
    </Box>
  );
}
