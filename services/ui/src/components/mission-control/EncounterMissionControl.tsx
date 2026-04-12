"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useOrgId } from "@/context/OrgContext";
import {
  fetchEncounterCodedLinks,
  fetchEncounterKPIs,
  fetchEncounterList,
  type EncounterCodedLink,
  type EncounterKPIs,
  type EncounterListItem,
  type EncounterListResponse,
} from "@/lib/missionControlApi";
import EncounterSearchPanel, { type EncounterSearchState } from "./EncounterSearchPanel";
import EncounterKpiStrip from "./EncounterKpiStrip";
import EncounterBatchBar from "./EncounterBatchBar";
import EncounterResultsTable from "./EncounterResultsTable";
import EncounterPreviewDialog from "./EncounterPreviewDialog";
import Score3DMap from "./Score3DMap";
import TrainingSetAdvisor, { type AppliedConfig } from "./TrainingSetAdvisor";
import { useEncounterBatch } from "./useEncounterBatch";

const DEFAULT_KPI: EncounterKPIs = {
  total_encounters: 0,
  total_patients: 0,
  coded_encounters: 0,
  median_codes_per_encounter: 0,
};
const RESULT_CAP = 1200;
const FETCH_PAGE_SIZE = 100;

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function buildDefaultSearch(): EncounterSearchState {
  const today = new Date();
  const yearAgo = new Date(today);
  yearAgo.setFullYear(today.getFullYear() - 1);
  return {
    query: "",
    dateFrom: isoDate(yearAgo),
    dateTo: isoDate(today),
    selectedYears: [],
    excludeNearDuplicates: false,
    nearDuplicateThreshold: "0.95",
    minCombinedScore: "0.05",
    minVectorScore: "",
    requireKeywordAnchor: false,
  };
}

export default function EncounterMissionControl() {
  const currentYear = new Date().getFullYear();
  const yearOptions = useMemo(() => [currentYear, currentYear - 1, currentYear - 2], [currentYear]);
  const orgId = useOrgId();

  const [search, setSearch] = useState<EncounterSearchState>(buildDefaultSearch);
  const [rows, setRows] = useState<EncounterListItem[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(100);
  const [selected, setSelected] = useState<Record<string, EncounterListItem>>({});
  const [loading, setLoading] = useState(false);
  const [kpis, setKpis] = useState<EncounterKPIs>(DEFAULT_KPI);
  const [kpisLoading, setKpisLoading] = useState(false);
  const [triggerAnalysis, setTriggerAnalysis] = useState(false);
  const [show3D, setShow3D] = useState(false);
  const [autoSearch, setAutoSearch] = useState(false);
  const [queryDiagnostics, setQueryDiagnostics] =
    useState<EncounterListResponse["query_diagnostics"]>(undefined);
  const [activePreview, setActivePreview] = useState<EncounterListItem | null>(null);
  const [previewCodedLinks, setPreviewCodedLinks] = useState<EncounterCodedLink[]>([]);
  const [previewLinksLoading, setPreviewLinksLoading] = useState(false);
  const [previewLinksError, setPreviewLinksError] = useState<string | null>(null);
  const lastBatchRefreshKeyRef = useRef<string>("");

  const selectedItems = useMemo(() => Object.values(selected), [selected]);

  const nearDuplicateThresholdValue = useMemo(() => {
    if (!search.excludeNearDuplicates) return undefined;
    const n = Number(search.nearDuplicateThreshold);
    return Number.isFinite(n) ? Math.min(0.99, Math.max(0.8, n)) : undefined;
  }, [search.excludeNearDuplicates, search.nearDuplicateThreshold]);

  const scoreValues = useMemo(() => {
    const combined = Number(search.minCombinedScore);
    const vector = Number(search.minVectorScore);
    return {
      minCombinedScore: Number.isFinite(combined) ? Math.min(1, Math.max(0, combined)) : undefined,
      minVectorScore: search.minVectorScore.trim() && Number.isFinite(vector)
        ? Math.min(1, Math.max(0, vector))
        : undefined,
    };
  }, [search.minCombinedScore, search.minVectorScore]);

  const buildSearchParams = useCallback(
    (page = 1, pageSize = 100) => ({
      orgId,
      dateFrom: search.dateFrom || undefined,
      dateTo: search.dateTo || undefined,
      query: search.query.trim() || undefined,
      page,
      pageSize,
      maxResults: RESULT_CAP,
      minCombinedScore: scoreValues.minCombinedScore,
      minVectorScore: scoreValues.minVectorScore,
      requireKeywordAnchor: search.requireKeywordAnchor,
      nearDuplicateThreshold: nearDuplicateThresholdValue,
    }),
    [orgId, search, scoreValues, nearDuplicateThresholdValue]
  );

  const { statuses, message, loading: batchLoading, runBatchForItems, runBatchAll } =
    useEncounterBatch({ triggerAnalysis, queryDiagnostics, buildSearchParams });

  const fetchAllEncounterRows = useCallback(async (): Promise<EncounterListResponse> => {
    const first = await fetchEncounterList(buildSearchParams(1, FETCH_PAGE_SIZE));
    const cap = Math.min(first.total, RESULT_CAP);
    if (cap <= first.items.length) {
      return {
        ...first,
        items: first.items.slice(0, cap),
      };
    }

    const allItems = [...first.items];
    const totalPages = Math.ceil(cap / FETCH_PAGE_SIZE);
    for (let pageNum = 2; pageNum <= totalPages; pageNum += 1) {
      const next = await fetchEncounterList(buildSearchParams(pageNum, FETCH_PAGE_SIZE));
      if (!next.items.length) break;
      allItems.push(...next.items);
      if (allItems.length >= cap) break;
    }

    return {
      ...first,
      items: allItems.slice(0, cap),
      total: cap,
      page: 1,
      page_size: FETCH_PAGE_SIZE,
    };
  }, [buildSearchParams]);

  const loadAll = useCallback(async (resetKpis = false) => {
    setLoading(true);
    if (resetKpis) setKpisLoading(true);
    try {
      const encountersFetch = fetchAllEncounterRows();
      const kpisFetch = resetKpis
        ? fetchEncounterKPIs({ orgId, dateFrom: search.dateFrom || undefined, dateTo: search.dateTo || undefined })
        : Promise.resolve(null);
      const [encounters, nextKpis] = await Promise.all([encountersFetch, kpisFetch]);
      setRows(encounters.items);
      setTotalResults(encounters.total);
      setQueryDiagnostics(encounters.query_diagnostics);
      if (nextKpis) setKpis(nextKpis);
      setSelected({});
    } catch (err) {
      setRows([]);
      setTotalResults(0);
      setQueryDiagnostics(undefined);
      console.error("Could not load encounters:", err);
    } finally {
      setLoading(false);
      if (resetKpis) setKpisLoading(false);
    }
  }, [fetchAllEncounterRows, orgId, search.dateFrom, search.dateTo]);

  const load = useCallback(() => {
    setPage(1);
    void loadAll(true);
  }, [loadAll]);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  const handleRowsPerPageChange = useCallback((newRpp: number) => {
    setRowsPerPage(newRpp);
    setPage(1);
  }, []);

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
    void fetchEncounterCodedLinks(activePreview.patient_id, activePreview.encounter_id)
      .then((links) => { if (mounted) setPreviewCodedLinks(links ?? []); })
      .catch((err) => {
        if (mounted) setPreviewLinksError(err instanceof Error ? err.message : "Could not load coded links.");
      })
      .finally(() => { if (mounted) setPreviewLinksLoading(false); });
    return () => { mounted = false; };
  }, [activePreview]);

  const toggleSelection = (item: EncounterListItem) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[item.encounter_id]) delete next[item.encounter_id];
      else next[item.encounter_id] = item;
      return next;
    });
  };

  const toggleYear = (year: number) => {
    setSearch((prev) => {
      const years = prev.selectedYears.includes(year)
        ? prev.selectedYears.filter((y) => y !== year)
        : [...prev.selectedYears, year];
      const sorted = years.sort((a, b) => a - b);
      return {
        ...prev,
        selectedYears: sorted,
        dateFrom: sorted.length ? `${Math.min(...sorted)}-01-01` : "",
        dateTo: sorted.length ? `${Math.max(...sorted)}-12-31` : "",
      };
    });
  };

  const isLoading = loading || batchLoading;
  const displayRows = useMemo(
    () => rows.slice((page - 1) * rowsPerPage, page * rowsPerPage),
    [rows, page, rowsPerPage]
  );
  const statusEntries = useMemo(() => Object.entries(statuses), [statuses]);
  const allBatchTerminal = useMemo(
    () =>
      statusEntries.length > 0 &&
      statusEntries.every(([, s]) => s === "completed" || s === "failed"),
    [statusEntries]
  );
  const anyBatchCompleted = useMemo(
    () => statusEntries.some(([, s]) => s === "completed"),
    [statusEntries]
  );
  const batchStatusKey = useMemo(
    () => statusEntries.map(([id, s]) => `${id}:${s}`).sort().join("|"),
    [statusEntries]
  );

  useEffect(() => {
    if (!autoSearch) return;
    setAutoSearch(false);
    void loadAll(true);
  }, [autoSearch, loadAll]);

  useEffect(() => {
    if (!allBatchTerminal || !anyBatchCompleted) return;
    if (!batchStatusKey || batchStatusKey === lastBatchRefreshKeyRef.current) return;
    lastBatchRefreshKeyRef.current = batchStatusKey;
    void loadAll(false);
  }, [allBatchTerminal, anyBatchCompleted, batchStatusKey, loadAll]);

  const handleThresholdDrag = useCallback((combined: number, vector?: number) => {
    setSearch((prev) => ({
      ...prev,
      minCombinedScore: combined.toFixed(2),
      minVectorScore: typeof vector === "number"
        ? vector.toFixed(2)
        : prev.minVectorScore === ""
          ? ""
          : prev.minVectorScore,
    }));
  }, []);

  const handleAdvisorApply = useCallback((config: AppliedConfig) => {
    setSearch((prev) => ({
      ...prev,
      minCombinedScore: config.minCombinedScore.toFixed(2),
      excludeNearDuplicates: config.enableDedup,
      nearDuplicateThreshold: config.dedupThreshold.toFixed(2),
    }));
    setAutoSearch(true);
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" component="h1" sx={{ mb: 2.5, fontWeight: 700 }}>
        Encounters
      </Typography>

      <Paper
        elevation={0}
        sx={{ p: 2.5, mb: 2.5, border: "1px solid", borderColor: "divider", borderRadius: 2 }}
      >
        <EncounterSearchPanel
          state={search}
          yearOptions={yearOptions}
          queryDiagnostics={queryDiagnostics}
          loading={isLoading}
          onQueryChange={(v) => setSearch((s) => ({ ...s, query: v }))}
          onDateFromChange={(v) => setSearch((s) => ({ ...s, dateFrom: v, selectedYears: [] }))}
          onDateToChange={(v) => setSearch((s) => ({ ...s, dateTo: v, selectedYears: [] }))}
          onToggleYear={toggleYear}
          onSearch={load}
        />
      </Paper>

      <EncounterKpiStrip kpis={kpis} loading={kpisLoading} />

      <Box sx={{ mt: 2.5 }}>
        <EncounterBatchBar
          selectedCount={selectedItems.length}
          totalResults={totalResults}
          loading={isLoading}
          triggerAnalysis={triggerAnalysis}
          onTriggerAnalysisChange={setTriggerAnalysis}
          statuses={statuses}
          message={message}
          onRunBatchSelected={() => runBatchForItems(selectedItems, "selected")}
          onRunBatchAll={() => void runBatchAll(totalResults)}
          onSelectAll={() => {
            const next: Record<string, EncounterListItem> = {};
            displayRows.forEach((r) => { next[r.encounter_id] = r; });
            setSelected(next);
          }}
          onClearSelection={() => setSelected({})}
          hasRows={rows.length > 0}
        />
      </Box>

      {rows.length > 0 && (
        <>
          <TrainingSetAdvisor
            rows={rows}
            currentMinScore={scoreValues.minCombinedScore ?? 0.2}
            onApply={handleAdvisorApply}
            onThresholdChange={handleThresholdDrag}
            onShow3D={() => setShow3D(true)}
          />
          <Score3DMap
            open={show3D}
            onClose={() => setShow3D(false)}
            rows={rows}
            minCombinedScore={scoreValues.minCombinedScore ?? 0.2}
            minVectorScore={scoreValues.minVectorScore}
            onEncounterSelect={(id) => {
              setShow3D(false);
              const item = rows.find((r) => r.encounter_id === id);
              if (item) setActivePreview(item);
            }}
          />
        </>
      )}

      {isLoading && <LinearProgress sx={{ mt: 2.5, mb: 1 }} />}
      {!isLoading && totalResults === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2.5, mb: 1 }}>
          Run a search to see encounters.
        </Typography>
      )}
      {rows.length >= RESULT_CAP && !isLoading && (
        <Alert severity="warning" sx={{ mt: 2.5, mb: 1, py: 0 }}>
          Result cap reached (1,200). Narrow your search for full coverage.
        </Alert>
      )}

      <EncounterResultsTable
        rows={displayRows}
        selected={selected}
        statuses={statuses}
        totalResults={rows.length}
        page={page}
        rowsPerPage={rowsPerPage}
        liveMinScore={scoreValues.minCombinedScore ?? 0.2}
        liveMinVectorScore={scoreValues.minVectorScore}
        lastSearchedMinScore={scoreValues.minCombinedScore ?? 0.2}
        lastSearchedMinVectorScore={scoreValues.minVectorScore}
        highlightedEncounterId={null}
        onToggleSelection={toggleSelection}
        onOpenPreview={setActivePreview}
        onPageChange={handlePageChange}
        onRowsPerPageChange={handleRowsPerPageChange}
      />

      <EncounterPreviewDialog
        item={activePreview}
        codedLinks={previewCodedLinks}
        loading={previewLinksLoading}
        error={previewLinksError}
        onClose={() => setActivePreview(null)}
      />
    </Box>
  );
}
