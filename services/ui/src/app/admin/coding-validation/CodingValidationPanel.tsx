/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 *
 * Wave E redesign: StatHero, SegmentedTabs filter, ReviewListCard rows,
 * DataGridCard expansion, ConfirmDialog on remove, Snackbar feedback,
 * EmptyState, SkeletonList loading.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";

import {
  DataGridCard,
  EmptyState,
  ReviewListCard,
  SegmentedTabs,
  SkeletonList,
  StatHero,
  type DataGridColumn,
  type ReviewListItem,
  type StatTile,
} from "@leo/design-system";
import ConfirmDialog from "@/components/ConfirmDialog";
import { getCodingValidation, updateGroundTruth } from "./api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FilterTab = "all" | "unresolved" | "safe_attached" | "withhold";

interface TopCandidate {
  term: string;
  concept_id: string;
  score: number;
  semantic_tag: string;
}

interface FactRow {
  id: string;
  caseId: string;
  surfaceForm: string;
  conceptId: string | null;
  preferredTerm: string | null;
  score: number | null;
  safeAttached: boolean;
  unresolvedReason: string | null;
  expectedWithhold: boolean;
  topCandidates: TopCandidate[];
}

interface SnackState {
  msg: string;
  severity: "success" | "error";
}

// ---------------------------------------------------------------------------
// Helpers (outside component -- no re-render cost)
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildRows(data: any): FactRow[] {
  if (!data?.cases) return [];
  const rows: FactRow[] = [];
  for (const c of data.cases) {
    for (const f of c.facts ?? []) {
      rows.push({
        id: `${c.case_id}__${f.surface_form}`,
        caseId: c.case_id,
        surfaceForm: String(f.surface_form ?? ""),
        conceptId: f.concept_id ?? null,
        preferredTerm: f.preferred_term ?? null,
        score: f.score ?? null,
        safeAttached: Boolean(f.safe_attached),
        unresolvedReason: f.unresolved_reason ?? null,
        expectedWithhold: Boolean(f.expected_withhold),
        topCandidates: f.top_candidates ?? [],
      });
    }
  }
  return rows;
}

function buildStats(rows: FactRow[]): StatTile[] {
  const total = rows.length;
  const safe = rows.filter((r) => r.safeAttached).length;
  const unresolved = rows.filter((r) => !r.safeAttached && !r.expectedWithhold).length;
  const withhold = rows.filter((r) => r.expectedWithhold).length;
  return [
    { id: "total", label: "Total terms", value: total },
    { id: "safe", label: "Safe attached", value: safe, tone: "positive" },
    {
      id: "unresolved",
      label: "Unresolved",
      value: unresolved,
      tone: unresolved > 0 ? "danger" : "neutral",
    },
    { id: "withhold", label: "Expected withhold", value: withhold, tone: "warning" },
  ];
}

function applyFilter(rows: FactRow[], tab: FilterTab): FactRow[] {
  if (tab === "safe_attached") return rows.filter((r) => r.safeAttached);
  if (tab === "unresolved") return rows.filter((r) => !r.safeAttached && !r.expectedWithhold);
  if (tab === "withhold") return rows.filter((r) => r.expectedWithhold);
  return rows;
}

function rowTone(row: FactRow): ReviewListItem["tone"] {
  if (row.safeAttached) return "positive";
  if (row.expectedWithhold) return "warning";
  return "danger";
}

function statusChip(row: FactRow) {
  if (row.safeAttached) return <Chip label="Safe attached" size="small" color="success" />;
  if (row.expectedWithhold) return <Chip label="Expected withhold" size="small" color="warning" />;
  return <Chip label="Unresolved" size="small" color="error" />;
}

const CANDIDATE_COLS: DataGridColumn<TopCandidate>[] = [
  {
    id: "term",
    header: "Term",
    render: (r) => <Typography variant="body2">{r.term}</Typography>,
  },
  {
    id: "concept_id",
    header: "Concept ID",
    render: (r) => <Typography variant="body2">{r.concept_id}</Typography>,
    width: "160px",
  },
  {
    id: "score",
    header: "Score",
    render: (r) => <Typography variant="body2">{r.score}</Typography>,
    width: "80px",
  },
  {
    id: "semantic_tag",
    header: "Semantic tag",
    render: (r) => <Typography variant="body2">{r.semantic_tag}</Typography>,
    width: "180px",
  },
];

// ---------------------------------------------------------------------------
// Row actions sub-component (keeps items useMemo cleaner)
// ---------------------------------------------------------------------------

function RowActions({
  row,
  onAccept,
  onRemove,
}: {
  row: FactRow;
  onAccept: (row: FactRow) => void;
  onRemove: (row: FactRow) => void;
}) {
  return (
    <Stack direction="row" spacing={0.5}>
      <IconButton
        size="small"
        color="success"
        aria-label={`Accept ${row.surfaceForm}`}
        onClick={(e) => { e.stopPropagation(); onAccept(row); }}
      >
        <CheckCircleOutlineIcon fontSize="small" />
      </IconButton>
      <IconButton
        size="small"
        color="error"
        aria-label={`Remove ${row.surfaceForm}`}
        onClick={(e) => { e.stopPropagation(); onRemove(row); }}
      >
        <DeleteOutlineIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

// LONG FUNCTION: orchestrates fetch, filter, and mutation state for
// the coding validation review surface.
export default function CodingValidationPanel() {
  const [allRows, setAllRows] = useState<FactRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<FilterTab>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<FactRow | null>(null);
  const [snack, setSnack] = useState<SnackState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCodingValidation();
      setAllRows(buildRows(res));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load validation data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleAccept = useCallback(async (row: FactRow) => {
    try {
      await updateGroundTruth(row.caseId, row.surfaceForm, "accept");
      setSnack({ msg: "Term accepted.", severity: "success" });
      await load();
    } catch (err) {
      setSnack({
        msg: `Failed to accept: ${err instanceof Error ? err.message : "unknown error"}`,
        severity: "error",
      });
    }
  }, [load]);

  const handleRemoveConfirm = useCallback(async () => {
    const row = pendingRemove;
    if (!row) return;
    setPendingRemove(null);
    try {
      await updateGroundTruth(row.caseId, row.surfaceForm, "remove");
      setSnack({ msg: "Term removed.", severity: "success" });
      await load();
    } catch (err) {
      setSnack({
        msg: `Failed to remove: ${err instanceof Error ? err.message : "unknown error"}`,
        severity: "error",
      });
    }
  }, [pendingRemove, load]);

  const stats = useMemo(() => buildStats(allRows), [allRows]);
  const visible = useMemo(() => applyFilter(allRows, tab), [allRows, tab]);

  const expandedRow = useMemo(
    () => allRows.find((r) => r.id === expandedId) ?? null,
    [allRows, expandedId],
  );

  const filterTabs = useMemo(
    () => [
      { id: "all", label: "All", count: allRows.length },
      {
        id: "unresolved",
        label: "Unresolved",
        count: allRows.filter((r) => !r.safeAttached && !r.expectedWithhold).length,
      },
      {
        id: "safe_attached",
        label: "Safe attached",
        count: allRows.filter((r) => r.safeAttached).length,
      },
      {
        id: "withhold",
        label: "Withhold",
        count: allRows.filter((r) => r.expectedWithhold).length,
      },
    ],
    [allRows],
  );

  const items = useMemo<ReviewListItem[]>(
    () =>
      visible.map((row) => ({
        id: row.id,
        title: row.surfaceForm,
        meta:
          row.conceptId
            ? `${row.conceptId} - ${row.preferredTerm ?? "-"}`
            : "No concept attached",
        chips: statusChip(row),
        tone: rowTone(row),
        selected: expandedId === row.id,
        onSelect: () => setExpandedId((prev) => (prev === row.id ? null : row.id)),
        actions: (
          <RowActions
            row={row}
            onAccept={handleAccept}
            onRemove={setPendingRemove}
          />
        ),
      })),
    [visible, expandedId, handleAccept],
  );

  if (loading) return <SkeletonList rows={6} />;
  if (error) return <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>;

  return (
    <Box>
      <StatHero stats={stats} />

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
          tabs={filterTabs}
          value={tab}
          onChange={(id) => setTab(id as FilterTab)}
          aria-label="Filter coding validation cases"
        />
      </Box>

      {visible.length === 0 ? (
        <EmptyState
          icon={<FactCheckOutlinedIcon sx={{ fontSize: 36 }} />}
          title="All terms validated"
          body="No coding validation cases to review."
        />
      ) : (
        <>
          <ReviewListCard items={items} />
          {expandedRow?.topCandidates?.length ? (
            <Box sx={{ mt: 1, mb: 2 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 0.75 }}
              >
                Top candidates for &quot;{expandedRow.surfaceForm}&quot;
              </Typography>
              <DataGridCard
                columns={CANDIDATE_COLS}
                rows={expandedRow.topCandidates}
                rowKey={(r) => r.concept_id}
              />
            </Box>
          ) : null}
        </>
      )}

      {pendingRemove ? (
        <ConfirmDialog
          title="Remove this term?"
          body="This affects the gold label set."
          confirmLabel="Remove"
          variant="danger"
          onConfirm={handleRemoveConfirm}
          onCancel={() => setPendingRemove(null)}
        />
      ) : null}

      <Snackbar
        open={snack !== null}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {snack ? (
          <Alert severity={snack.severity} onClose={() => setSnack(null)}>
            {snack.msg}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
}
