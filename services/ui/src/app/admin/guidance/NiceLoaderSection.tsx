/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E647765A")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";

import {
  DataGridCard,
  EmptyState,
  ProgressiveReveal,
  ProgressStrip,
  ToolbarActions,
  useMotion,
  type DataGridColumn,
} from "@leo/design-system";

import TaxonomyBrowserDrawer from "./TaxonomyBrowserDrawer";
import { bounceInteraction, popVariants } from "./motionPresets";

interface GuidelineOption { code: string; title: string; type: string; }

interface Job {
  job_id: string;
  code: string;
  status: string;
  step?: string;
  completed_at?: string | null;
  recommendation_count?: number;
}

/** NICE code pattern: NG12, CG89, TA123, etc. */
const NICE_CODE_RE = /^(NG|CG|TA|DG|IPG|QS|PH|SC|MTG|LGB|HSG|MPG|ES)\d+$/i;

function isNiceCode(value: string): boolean {
  return NICE_CODE_RE.test(value.trim());
}

const JOB_COLUMNS: DataGridColumn<Job>[] = [
  {
    id: "code",
    header: "Code",
    width: "90px",
    render: (j) => <Chip label={j.code} size="small" color="primary" variant="outlined" />,
  },
  {
    id: "step",
    header: "Step",
    render: (j) => <Typography variant="body2">{j.step ?? "--"}</Typography>,
  },
  {
    id: "status",
    header: "Status",
    width: "110px",
    render: (j) => (
      <Chip
        label={j.status}
        size="small"
        color={j.status === "done" ? "success" : j.status === "error" ? "error" : "default"}
      />
    ),
  },
  {
    id: "recs",
    header: "Recommendations",
    align: "right" as const,
    width: "150px",
    render: (j) => (
      <Typography variant="body2">{j.recommendation_count ?? "--"}</Typography>
    ),
  },
  {
    id: "date",
    header: "Date",
    width: "110px",
    render: (j) => (
      <Typography variant="body2">
        {j.completed_at ? new Date(j.completed_at).toLocaleDateString() : "--"}
      </Typography>
    ),
  },
];

interface Props { onGuidelineLoaded?: () => void; }

export default function NiceLoaderSection({ onGuidelineLoaded }: Props) {
  const { reducedMotion } = useMotion();
  const [inputValue, setInputValue] = useState("");
  const [catalogueOptions, setCatalogueOptions] = useState<GuidelineOption[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ingestLog, setIngestLog] = useState<string[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [refreshJobs, setRefreshJobs] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);

  // Debounced catalogue search
  useEffect(() => {
    const t = setTimeout(() => {
      if (inputValue.length < 2) { setCatalogueOptions([]); return; }
      setSearchError(null);
      fetch(`/api/nice/catalogue?q=${encodeURIComponent(inputValue)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
        .then((data: GuidelineOption[]) => setCatalogueOptions(data))
        .catch(() => { setCatalogueOptions([]); setSearchError("Could not search for guidelines. Try again."); });
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

  const handleBrowseSelect = useCallback((code: string) => {
    setBrowseOpen(false);
    setInputValue(code);
  }, []);

  const handleIngest = useCallback(async () => {
    const code = inputValue.trim().toUpperCase();
    if (!code) return;
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
        const d = JSON.parse((e as MessageEvent).data);
        setIngestLog((prev) => [...prev, d.step]);
      });
      es.addEventListener("done", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
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
  }, [inputValue, onGuidelineLoaded]);

  const canLoad = !loading && isNiceCode(inputValue);

  return (
    <Box>
      {/* -- Secondary actions -------------------------------------------- */}
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end" sx={{ mb: 1.5 }}>
        <ToolbarActions
          actions={[
            { id: "sync", label: syncing ? "Refreshing..." : "Refresh guideline list", variant: "secondary", onClick: handleSync, disabled: syncing, loading: syncing },
            { id: "browse", label: "Browse by area", variant: "secondary", onClick: () => setBrowseOpen(true), icon: <AccountTreeOutlinedIcon fontSize="small" /> },
          ]}
        />
      </Stack>

      {syncMessage && (
        <Alert severity={syncMessage.includes("failed") || syncMessage.includes("Could not") ? "error" : "success"} sx={{ mb: 1.5 }} onClose={() => setSyncMessage(null)}>
          {syncMessage}
        </Alert>
      )}
      {searchError && <Alert severity="error" sx={{ mb: 1.5 }}>{searchError}</Alert>}

      {/* -- Search + load ------------------------------------------------ */}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "flex-start" }} sx={{ mb: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Autocomplete
            freeSolo
            options={catalogueOptions}
            getOptionLabel={(opt) =>
              typeof opt === "string" ? opt : `${opt.code} -- ${opt.title}`
            }
            inputValue={inputValue}
            onInputChange={(_, value, reason) => {
                if (reason !== "reset") setInputValue(value);
              }}
            onChange={(_, value) => {
              if (value && typeof value !== "string" && value.code) {
                setInputValue(value.code);
              }
            }}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                placeholder="e.g. bowel cancer or NG151"
                aria-label="Search for a NICE guideline"
                onKeyDown={(e) => { if (e.key === "Enter" && canLoad) handleIngest(); }}
              />
            )}
          />
        </Box>
        <fm.div style={{ display: "inline-block" }} {...bounceInteraction(reducedMotion || !canLoad)}>
          <ToolbarActions
            actions={[
              { id: "load", label: "Load this guideline", variant: "primary", onClick: handleIngest, disabled: !canLoad, loading },
            ]}
          />
        </fm.div>
      </Stack>

      {/* -- Progress strip + log ----------------------------------------- */}
      {loading && (
        <Box sx={{ mb: 2 }}>
          <ProgressStrip
            label={ingestLog[ingestLog.length - 1] ?? "Loading..."}
            value={ingestLog.length}
            total={Math.max(ingestLog.length, 8)}
            tone="neutral"
          />
          <Box sx={{ mt: 1 }}>
            <ProgressiveReveal summary="Show progress details">
              <Box sx={{ fontFamily: "monospace", fontSize: "0.75rem", bgcolor: "grey.50", p: 1, borderRadius: 1, mt: 1 }}>
                <AnimatePresence initial={false}>
                  {ingestLog.map((line, i) => (
                    <fm.div
                      key={`${i}-${line}`}
                      variants={popVariants(reducedMotion)}
                      initial="initial"
                      animate="animate"
                      exit="exit"
                    >
                      {line}
                    </fm.div>
                  ))}
                </AnimatePresence>
              </Box>
            </ProgressiveReveal>
          </Box>
        </Box>
      )}

      {!loading && ingestLog.length > 0 && (
        <Alert severity="success" sx={{ mb: 2 }}>{ingestLog[ingestLog.length - 1]}</Alert>
      )}

      {jobsError && <Alert severity="error" sx={{ mb: 2 }}>{jobsError}</Alert>}

      {/* -- Recent jobs -------------------------------------------------- */}
      {jobs.length > 0 ? (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            Recent loads
          </Typography>
          <DataGridCard
            columns={JOB_COLUMNS}
            rows={jobs}
            rowKey={(j) => j.job_id}
            dense
          />
        </Box>
      ) : (
        <EmptyState
          icon={
            <fm.div
              animate={reducedMotion ? undefined : { y: [0, -6, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            >
              <HistoryOutlinedIcon fontSize="large" />
            </fm.div>
          }
          title="No recent loads"
          body="Loaded guidelines appear here."
          data-testid="jobs-empty"
        />
      )}

      <TaxonomyBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onSelectGuideline={handleBrowseSelect}
      />
    </Box>
  );
}
