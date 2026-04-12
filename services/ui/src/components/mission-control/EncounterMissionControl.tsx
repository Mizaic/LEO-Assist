"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useOrgId } from "@/context/OrgContext";
import {
  batchResetAndRecodeEncounters,
  fetchEncounterCodedLinks,
  fetchEncounterKPIs,
  fetchEncounterList,
  type EncounterCodedLink,
  type EncounterListItem,
  type EncounterListResponse,
} from "@/lib/missionControlApi";

type JobState = "queued" | "running" | "completed" | "failed";

export default function EncounterMissionControl() {
  const currentYear = new Date().getFullYear();
  const yearOptions = useMemo(
    () => [currentYear, currentYear - 1, currentYear - 2],
    [currentYear]
  );
  const orgId = useOrgId();
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [rows, setRows] = useState<EncounterListItem[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [selected, setSelected] = useState<Record<string, EncounterListItem>>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [kpis, setKpis] = useState({
    total_encounters: 0,
    total_patients: 0,
    coded_encounters: 0,
    median_codes_per_encounter: 0,
  });
  const [triggerAnalysis, setTriggerAnalysis] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, JobState>>({});
  const [queryDiagnostics, setQueryDiagnostics] =
    useState<EncounterListResponse["query_diagnostics"]>(undefined);
  const [activePreview, setActivePreview] = useState<EncounterListItem | null>(null);
  const [previewCodedLinks, setPreviewCodedLinks] = useState<EncounterCodedLink[]>([]);
  const [previewLinksLoading, setPreviewLinksLoading] = useState(false);
  const [previewLinksError, setPreviewLinksError] = useState<string | null>(null);

  const selectedItems = useMemo(() => Object.values(selected), [selected]);
  const completedCount = Object.values(statuses).filter((s) => s === "completed").length;
  const failedCount = Object.values(statuses).filter((s) => s === "failed").length;
  const runningCount = Object.values(statuses).filter((s) => s === "running").length;
  const queuedCount = Object.values(statuses).filter((s) => s === "queued").length;

  const load = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const [encounters, nextKpis] = await Promise.all([
        fetchEncounterList({
          orgId,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          query: query.trim() || undefined,
          page: 1,
          pageSize: 100,
        }),
        fetchEncounterKPIs({
          orgId,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
        }),
      ]);
      setRows(encounters.items);
      setTotalResults(encounters.total);
      setQueryDiagnostics(encounters.query_diagnostics);
      setKpis(nextKpis);
      setSelected({});
      setStatuses({});
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not load encounters.");
      setRows([]);
      setTotalResults(0);
      setQueryDiagnostics(undefined);
    } finally {
      setLoading(false);
    }
  }, [orgId, dateFrom, dateTo, query]);

  const toggleSelection = (item: EncounterListItem) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[item.encounter_id]) delete next[item.encounter_id];
      else next[item.encounter_id] = item;
      return next;
    });
  };

  const openPreview = (item: EncounterListItem) => {
    setActivePreview(item);
  };

  useEffect(() => {
    if (!activePreview) {
      setPreviewCodedLinks([]);
      setPreviewLinksLoading(false);
      setPreviewLinksError(null);
      return;
    }
    let mounted = true;
    setPreviewLinksLoading(true);
    setPreviewLinksError(null);
    setPreviewCodedLinks([]);
    void fetchEncounterCodedLinks(activePreview.patient_id, activePreview.encounter_id)
      .then((rows) => {
        if (!mounted) {
          return;
        }
        setPreviewCodedLinks(rows ?? []);
      })
      .catch((err) => {
        if (!mounted) {
          return;
        }
        setPreviewLinksError(
          err instanceof Error ? err.message : "Could not load coded links."
        );
      })
      .finally(() => {
        if (mounted) {
          setPreviewLinksLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [activePreview]);

  const selectAllVisibleRows = () => {
    const next: Record<string, EncounterListItem> = {};
    rows.forEach((row) => {
      next[row.encounter_id] = row;
    });
    setSelected(next);
  };

  const clearSelection = () => {
    setSelected({});
  };

  const toggleYear = (year: number) => {
    setSelectedYears((prev) => {
      const exists = prev.includes(year);
      const next = exists ? prev.filter((y) => y !== year) : [...prev, year];
      if (!next.length) {
        setDateFrom("");
        setDateTo("");
        return [];
      }
      const minYear = Math.min(...next);
      const maxYear = Math.max(...next);
      setDateFrom(`${minYear}-01-01`);
      setDateTo(`${maxYear}-12-31`);
      return next.sort((a, b) => a - b);
    });
  };

  const subscribeToRun = (runId: string, encounterId: string) => {
    const source = new EventSource(
      `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(runId)}`
    );
    const mark = (state: JobState) =>
      setStatuses((prev) => ({ ...prev, [encounterId]: state }));

    const onEvent = (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data) as { type?: string };
        const type = payload.type ?? "";
        if (type === "run_started" || type === "patient_started" || type === "encounter_started") {
          mark("running");
        }
        if (type === "run_completed" || type === "pipeline_done" || type === "extraction_done") {
          mark("completed");
          source.close();
        }
        if (type === "pipeline_error" || type === "run_error") {
          mark("failed");
          source.close();
        }
      } catch {
        // Ignore malformed progress events.
      }
    };
    source.addEventListener("run_started", onEvent as EventListener);
    source.addEventListener("patient_started", onEvent as EventListener);
    source.addEventListener("encounter_started", onEvent as EventListener);
    source.addEventListener("run_completed", onEvent as EventListener);
    source.addEventListener("pipeline_done", onEvent as EventListener);
    source.addEventListener("extraction_done", onEvent as EventListener);
    source.addEventListener("pipeline_error", onEvent as EventListener);
    source.addEventListener("run_error", onEvent as EventListener);
    source.onerror = () => {
      mark("failed");
      source.close();
    };
  };

  const runBatch = async () => {
    if (!selectedItems.length) {
      setMessage("Select at least one encounter first.");
      return;
    }
    setMessage(null);
    const items = selectedItems.map((item) => ({
      patient_id: item.patient_id,
      encounter_id: item.encounter_id,
    }));
    try {
      const result = await batchResetAndRecodeEncounters(
        items,
        triggerAnalysis,
        queryDiagnostics
      );
      const initial: Record<string, JobState> = {};
      result.queued.forEach((job) => {
        initial[job.encounter_id] = "queued";
      });
      result.failed.forEach((job) => {
        initial[job.encounter_id] = "failed";
      });
      setStatuses(initial);
      result.queued.forEach((job) => subscribeToRun(job.run_id, job.encounter_id));
      setMessage(
        `Batch queued: ${result.queued_count} queued, ${result.failed_count} failed.`
      );
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Batch reset and recode failed."
      );
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Encounters
      </Typography>
      <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
        <TextField
          label="Search encounters (hybrid)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              void load();
            }
          }}
          size="small"
          sx={{ minWidth: 320 }}
        />
        <TextField
          label="From"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          size="small"
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          label="To"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          size="small"
          InputLabelProps={{ shrink: true }}
        />
        <Button variant="contained" onClick={load} disabled={loading}>
          Search
        </Button>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ alignSelf: "center" }}>
          Quick years:
        </Typography>
        {yearOptions.map((year) => (
          <Chip
            key={year}
            label={String(year)}
            clickable
            color={selectedYears.includes(year) ? "primary" : "default"}
            variant={selectedYears.includes(year) ? "filled" : "outlined"}
            onClick={() => toggleYear(year)}
          />
        ))}
      </Stack>
      {queryDiagnostics && (
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
          <Chip
            size="small"
            label={`Original: ${queryDiagnostics.original_query}`}
            variant="outlined"
          />
          <Chip
            size="small"
            color={queryDiagnostics.rewrite_applied ? "info" : "default"}
            label={`Rewritten: ${queryDiagnostics.rewritten_query}`}
          />
          <Chip
            size="small"
            label={`Source: ${queryDiagnostics.rewrite_source}`}
            variant="outlined"
          />
        </Stack>
      )}

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <Card><CardContent><Typography variant="caption">Encounters</Typography><Typography variant="h6">{kpis.total_encounters}</Typography></CardContent></Card>
        <Card><CardContent><Typography variant="caption">Patients</Typography><Typography variant="h6">{kpis.total_patients}</Typography></CardContent></Card>
        <Card><CardContent><Typography variant="caption">Coded</Typography><Typography variant="h6">{kpis.coded_encounters}</Typography></CardContent></Card>
        <Card><CardContent><Typography variant="caption">Median codes</Typography><Typography variant="h6">{kpis.median_codes_per_encounter.toFixed(1)}</Typography></CardContent></Card>
      </Stack>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center">
          <Button variant="contained" color="warning" onClick={runBatch}>
            Reset + recode selected ({selectedItems.length})
          </Button>
          <Button variant="outlined" onClick={selectAllVisibleRows} disabled={!rows.length}>
            Select all results
          </Button>
          <Button variant="text" onClick={clearSelection} disabled={!selectedItems.length}>
            Clear selection
          </Button>
          <Typography variant="body2">Also rerun analytics</Typography>
          <Switch
            checked={triggerAnalysis}
            onChange={(e) => setTriggerAnalysis(e.target.checked)}
          />
          {message && <Typography variant="body2">{message}</Typography>}
        </Stack>
        {!!Object.keys(statuses).length && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2">
              Queued {queuedCount} | Running {runningCount} | Completed {completedCount} |
              Failed {failedCount}
            </Typography>
          </Box>
        )}
      </Paper>

      {loading && <LinearProgress sx={{ mb: 1 }} />}
      <Typography variant="body2" sx={{ mb: 1 }}>
        Search results: {totalResults} (showing {rows.length})
      </Typography>
      <Paper>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Pick</TableCell>
              <TableCell>Date</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Match</TableCell>
              <TableCell>Coded links</TableCell>
              <TableCell>Progress</TableCell>
              <TableCell>Text</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow
                key={row.encounter_id}
                hover
                onClick={() => openPreview(row)}
                sx={{ cursor: "pointer" }}
              >
                <TableCell>
                  <Switch
                    size="small"
                    checked={Boolean(selected[row.encounter_id])}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggleSelection(row)}
                  />
                </TableCell>
                <TableCell>{row.encounter_date ?? "-"}</TableCell>
                <TableCell>{row.patient_id}</TableCell>
                <TableCell>
                  <Chip size="small" label={row.match_type} />
                </TableCell>
                <TableCell>{row.coded_count}</TableCell>
                <TableCell>{statuses[row.encounter_id] ?? "-"}</TableCell>
                <TableCell sx={{ maxWidth: 520 }}>
                  <Typography variant="body2" noWrap title={row.text ?? ""}>
                    {row.text ?? ""}
                  </Typography>
                  {!!row.match_rationale?.length && (
                    <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: "wrap" }}>
                      {row.match_rationale.slice(0, 4).map((term) => (
                        <Chip key={`${row.encounter_id}-${term}`} size="small" label={term} variant="outlined" />
                      ))}
                    </Stack>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Dialog
        open={Boolean(activePreview)}
        onClose={() => setActivePreview(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Encounter preview</DialogTitle>
        <DialogContent dividers>
          {activePreview && (
            <Stack spacing={1.5}>
              <Typography variant="body2">
                Date: {activePreview.encounter_date ?? "-"}
              </Typography>
              <Typography variant="body2">
                Patient: {activePreview.patient_id}
              </Typography>
              <Typography variant="body2">
                Encounter ID: {activePreview.encounter_id}
              </Typography>
              <Typography variant="body2">
                Match: {activePreview.match_type}
              </Typography>
              <Typography variant="body2">
                Coded links: {activePreview.coded_count}
              </Typography>
              {previewLinksLoading && (
                <Typography variant="body2" color="text.secondary">
                  Loading coded terms...
                </Typography>
              )}
              {previewLinksError && (
                <Typography variant="body2" color="error">
                  {previewLinksError}
                </Typography>
              )}
              {!!previewCodedLinks.length && (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
                  {previewCodedLinks.map((item) => {
                    const term = (item.term || item.concept_id || "unknown").trim();
                    const assertion = (item.assertion || "present").trim();
                    const label = `${term} (${assertion})`;
                    return (
                      <Chip
                        key={`${activePreview.encounter_id}-${item.concept_id}-${assertion}`}
                        size="small"
                        label={label}
                        variant="outlined"
                        title={`${term} | ${item.concept_id}`}
                      />
                    );
                  })}
                </Stack>
              )}
              <Typography variant="subtitle2">Encounter text</Typography>
              <Paper variant="outlined" sx={{ p: 1.5, maxHeight: 320, overflow: "auto" }}>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {activePreview.text?.trim() || "No encounter text available."}
                </Typography>
              </Paper>
              {!!activePreview.match_rationale?.length && (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
                  {activePreview.match_rationale.map((term) => (
                    <Chip
                      key={`preview-${activePreview.encounter_id}-${term}`}
                      size="small"
                      label={term}
                      variant="outlined"
                    />
                  ))}
                </Stack>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setActivePreview(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
