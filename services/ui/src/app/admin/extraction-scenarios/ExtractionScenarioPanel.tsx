/**
 * Extraction Scenario Panel -- list + run validation.
 *
 * Provides:
 *   - StatHero: total / approved / awaiting / latest F1 tiles
 *   - SegmentedTabs: All | Awaiting review | Approved
 *   - ToolbarActions: Run validation (primary), search input
 *   - DataGridCard: case rows with Review action -> CaseReviewDrawer
 *   - RunResultsDrawer: opens on "Run validation"
 *
 * Atlas: DI (pending), VAL-87173594, VT-29880CC8.
 * Audience: clinicians and QA staff (UK reading age 11 copy).
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import AddIcon from "@mui/icons-material/Add";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import IconButton from "@mui/material/IconButton";

import ConfirmDialog from "@/components/ConfirmDialog";

import {
  DataGridCard,
  FilterBar,
  SegmentedTabs,
  SkeletonList,
  StatHero,
  ToolbarActions,
  type DataGridColumn,
  type FilterChip,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import { deleteScenario, listScenarios, triggerRun } from "./api";
import type {
  ExtractionScenarioRow,
  ScenarioListResponse,
  StatusFilter,
  ValidationRunStatus,
} from "./types";
import CaseReviewDrawer from "./CaseReviewDrawer";
import QuickTestDrawer from "./QuickTestDrawer";
import RunResultsDrawer from "./RunResultsDrawer";
import ScenarioEditorDialog from "./ScenarioEditorDialog";

const EMPTY_LIST: ScenarioListResponse = {
  total: 0,
  approved: 0,
  draft: 0,
  pass_threshold: 0.95,
  cases: [],
};

const STATUS_LABEL: Record<StatusFilter, string> = {
  all: "All",
  approved: "Approved",
  draft: "Awaiting review",
};

function reviewStatusChip(row: ExtractionScenarioRow) {
  const approved = row.review_status === "approved";
  return (
    <Chip
      size="small"
      label={approved ? "Approved" : "Awaiting review"}
      color={approved ? "success" : "default"}
      variant="outlined"
      data-testid={`status-chip-${row.case_id}`}
      sx={{ fontWeight: 500 }}
    />
  );
}

function difficultyChips(row: ExtractionScenarioRow) {
  if (!row.difficulty?.length) return null;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap">
      {row.difficulty.map((d) => (
        <Chip key={d} size="small" label={d.replace(/_/g, " ")} variant="outlined" />
      ))}
    </Stack>
  );
}

// LONG FUNCTION: panel orchestrates fetch, filter, run trigger, and 3 drawers.
export default function ExtractionScenarioPanel() {
  const [data, setData] = useState<ScenarioListResponse>(EMPTY_LIST);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<"create" | "edit">("create");
  const [editorCaseId, setEditorCaseId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [runDrawerOpen, setRunDrawerOpen] = useState(false);
  const [currentRun, setCurrentRun] = useState<ValidationRunStatus | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [quickTestOpen, setQuickTestOpen] = useState(false);
  const [difficultyFilter, setDifficultyFilter] = useState<Set<string>>(
    new Set(),
  );

  const toggleDifficulty = useCallback((id: string) => {
    setDifficultyFilter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(null);
    listScenarios({
      status: statusFilter === "all" ? undefined : statusFilter,
      search: search || undefined,
    })
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Could not load scenarios.");
      })
      .finally(() => setLoading(false));
  }, [statusFilter, search, refreshKey]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRunValidation = useCallback(async () => {
    setTriggering(true);
    setError(null);
    try {
      const result = await triggerRun("all");
      setCurrentRun({
        run_id: result.run_id,
        status: "queued",
        progress: 0,
        triggered_by: "ui",
        triggered_at: new Date().toISOString(),
        pass_threshold: data.pass_threshold,
      });
      setRunDrawerOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the validation run.");
    } finally {
      setTriggering(false);
    }
  }, [data.pass_threshold]);

  const openCreateEditor = useCallback(() => {
    setEditorMode("create");
    setEditorCaseId(null);
    setEditorOpen(true);
  }, []);

  const openEditEditor = useCallback((caseId: string) => {
    setEditorMode("edit");
    setEditorCaseId(caseId);
    setEditorOpen(true);
  }, []);

  const handleDeleteScenario = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteScenario(deleteTarget);
      setDeleteTarget(null);
      setRefreshKey((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this scenario.");
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget]);

  const stats: StatTile[] = useMemo(
    () => [
      { id: "total", label: "Total cases", value: data.total, tone: "neutral" },
      {
        id: "approved",
        label: "Approved",
        value: data.approved,
        tone: data.approved === data.total && data.total > 0 ? "positive" : "neutral",
      },
      {
        id: "draft",
        label: "Awaiting review",
        value: data.draft,
        tone: data.draft > 0 ? "warning" : "positive",
      },
      {
        id: "threshold",
        label: "Pass threshold",
        value: `${(data.pass_threshold * 100).toFixed(0)}% F1`,
        tone: "neutral",
      },
    ],
    [data],
  );

  const filterTabs = useMemo(
    () => [
      { id: "all", label: STATUS_LABEL.all, count: data.total },
      { id: "draft", label: STATUS_LABEL.draft, count: data.draft },
      { id: "approved", label: STATUS_LABEL.approved, count: data.approved },
    ],
    [data],
  );

  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "new-scenario",
        label: "New scenario",
        icon: <AddIcon fontSize="small" />,
        variant: "primary",
        onClick: openCreateEditor,
      },
      {
        id: "run-validation",
        label: triggering ? "Starting..." : "Run validation",
        icon: triggering ? (
          <CircularProgress size={14} color="inherit" />
        ) : (
          <PlayCircleOutlineIcon fontSize="small" />
        ),
        onClick: handleRunValidation,
        disabled: triggering,
      },
      {
        id: "quick-test",
        label: "Quick test",
        icon: <ScienceOutlinedIcon fontSize="small" />,
        onClick: () => setQuickTestOpen(true),
      },
    ],
    [handleRunValidation, openCreateEditor, triggering],
  );

  const difficultyChipsDef: FilterChip[] = useMemo(
    () =>
      ["easy", "medium", "hard"].map((id) => ({
        id,
        label: id.charAt(0).toUpperCase() + id.slice(1),
        active: difficultyFilter.has(id),
        onToggle: () => toggleDifficulty(id),
      })),
    [difficultyFilter, toggleDifficulty],
  );

  const visibleCases = useMemo(() => {
    if (difficultyFilter.size === 0) return data.cases;
    return data.cases.filter((row) =>
      row.difficulty?.some((d) => difficultyFilter.has(d.toLowerCase())),
    );
  }, [data.cases, difficultyFilter]);

  const columns: DataGridColumn<ExtractionScenarioRow>[] = useMemo(
    () => [
      {
        id: "case_id",
        header: "Case ID",
        render: (row) => (
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {row.case_id}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.format}
            </Typography>
          </Box>
        ),
      },
      {
        id: "site",
        header: "Site",
        width: "140px",
        render: (row) => (
          <Typography variant="body2">{row.site.replace(/_/g, " ")}</Typography>
        ),
      },
      {
        id: "difficulty",
        header: "Difficulty",
        render: (row) => difficultyChips(row),
      },
      {
        id: "expected",
        header: "# phrases",
        width: "96px",
        render: (row) => (
          <Typography variant="body2">{row.expected_strings?.length ?? 0}</Typography>
        ),
      },
      {
        id: "status",
        header: "Review status",
        width: "180px",
        render: (row) => reviewStatusChip(row),
      },
      {
        id: "actions",
        header: "",
        align: "right" as const,
        width: "180px",
        render: (row) => (
          <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
            <Button
              variant="text"
              size="small"
              onClick={() => setReviewingId(row.case_id)}
              data-testid={`review-btn-${row.case_id}`}
              sx={{ fontWeight: 500, textTransform: "none", minWidth: 0 }}
            >
              Review
            </Button>
            <IconButton
              aria-label={`Edit ${row.case_id}`}
              size="small"
              onClick={() => openEditEditor(row.case_id)}
              data-testid={`edit-btn-${row.case_id}`}
            >
              <EditOutlinedIcon fontSize="small" />
            </IconButton>
            <IconButton
              aria-label={`Delete ${row.case_id}`}
              size="small"
              onClick={() => setDeleteTarget(row.case_id)}
              data-testid={`delete-btn-${row.case_id}`}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Stack>
        ),
      },
    ],
    [openEditEditor],
  );

  const emptyState = (
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        No scenarios found.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        The knowledge graph may still be seeding. Try refreshing.
      </Typography>
    </Box>
  );

  return (
    <Box data-testid="extraction-scenario-panel">
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
          tabs={filterTabs}
          value={statusFilter}
          onChange={(id) => setStatusFilter(id as StatusFilter)}
          aria-label="Filter scenarios by review status"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      <Box sx={{ mb: 2 }}>
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Search by case ID or site..."
          aria-label="Search and filter scenarios"
          chips={difficultyChipsDef}
        />
      </Box>

      {loading ? (
        <SkeletonList rows={4} />
      ) : (
        <DataGridCard<ExtractionScenarioRow>
          columns={columns}
          rows={visibleCases}
          rowKey={(row) => row.case_id}
          emptyState={emptyState}
        />
      )}

      <CaseReviewDrawer
        caseId={reviewingId}
        open={reviewingId !== null}
        onClose={() => setReviewingId(null)}
        onApproved={() => {
          setReviewingId(null);
          setRefreshKey((n) => n + 1);
        }}
        onEdit={(id) => {
          setReviewingId(null);
          openEditEditor(id);
        }}
      />

      <RunResultsDrawer
        run={currentRun}
        open={runDrawerOpen}
        onClose={() => setRunDrawerOpen(false)}
        onRunUpdate={setCurrentRun}
      />

      <QuickTestDrawer
        open={quickTestOpen}
        onClose={() => setQuickTestOpen(false)}
      />

      <ScenarioEditorDialog
        open={editorOpen}
        mode={editorMode}
        caseId={editorCaseId}
        onClose={() => setEditorOpen(false)}
        onSaved={() => setRefreshKey((n) => n + 1)}
      />

      {deleteTarget ? (
        <ConfirmDialog
          title="Delete extraction scenario?"
          body={`This permanently removes ${deleteTarget} from the validation corpus.`}
          confirmLabel={deleting ? "Deleting..." : "Delete scenario"}
          variant="danger"
          onConfirm={handleDeleteScenario}
          onCancel={() => setDeleteTarget(null)}
        />
      ) : null}
    </Box>
  );
}
