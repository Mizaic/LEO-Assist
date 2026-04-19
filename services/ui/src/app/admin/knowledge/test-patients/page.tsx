"use client";

/**
 * Knowledge > Test Patients -- the centralised test patient library.
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: one tile per aspect (All / Reading notes / Patient
 *     story / Rule checks / SBAR handover).
 *   - SegmentedTabs: aspect filter, drives the row query.
 *   - ToolbarActions: Build / Copy from a real patient (Phase A:
 *     surfaced but disabled until Phase B-D land per-aspect builders).
 *   - DataGridCard: list of saved test patients with Source / Aspect
 *     chips, age + sex, created_by, and a per-row Delete action.
 *
 * Phase A scope (this PR):
 *   - Aspect filter + count tiles wired to /test-patients endpoints.
 *   - Table of saved test patients with the test_ prefix and aspect
 *     chip clearly visible.
 *
 * The legacy /admin/guidance/test-patients route is removed in this
 * same change set; the supporting dialog modules under
 * services/ui/src/app/admin/guidance/test-patients/ are still the
 * source of truth for the Guidelines aspect and will be re-mounted
 * here in Phase B.
 *
 * Atlas IDs: UN-50102672, DI-7625C251, DO-EE2C2EA1, R-8C0CC94B,
 * VT-5BDFE5F7.
 *
 * Audience (UK reading age 11): all visible copy is plain English.
 * Technical concepts (aspect, replay) are translated in helper text.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import FileCopyOutlinedIcon from "@mui/icons-material/FileCopyOutlined";

import {
  DataGridCard,
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type DataGridColumn,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import {
  ASPECT_HINT,
  ASPECT_LABEL,
  ASPECT_VALUES,
  type AspectCounts,
  type AspectFilter,
  type TestPatientRow,
} from "./types";
import {
  deleteTestPatient,
  getAspectCounts,
  listTestPatients,
} from "./api";
import BuildPatientDialog from "./BuildPatientDialog";
import CopyFromRealDialog from "./CopyFromRealDialog";

const ZERO_COUNTS: AspectCounts = {
  all: 0,
  nlp: 0,
  episodes: 0,
  guidelines: 0,
  summarisation: 0,
};

function buildStats(counts: AspectCounts): StatTile[] {
  return ASPECT_VALUES.map((key) => {
    const value = counts[key as keyof AspectCounts] ?? 0;
    const tone: StatTile["tone"] =
      key === "all" ? "neutral" : value > 0 ? "positive" : "neutral";
    return {
      id: key,
      label: ASPECT_LABEL[key],
      value,
      hint: ASPECT_HINT[key],
      tone,
    };
  });
}

function sourceChipLabel(row: TestPatientRow): string {
  if (row.generation_source === "cloned") return "Copied from real";
  if (row.generation_source === "manual") return "Built by hand";
  return row.generation_source ?? "-";
}

function ageSex(row: TestPatientRow): string {
  const age = row.age != null ? `${row.age}y` : "-";
  const sex = row.sex ?? "-";
  return `${age} / ${sex}`;
}

// LONG FUNCTION: page orchestrates fetch, filter, and 4 callbacks.
// Splitting further would scatter the load/refresh state across files.
export default function TestPatientLibraryKnowledgeTab() {
  const [aspect, setAspect] = useState<AspectFilter>("all");
  const [counts, setCounts] = useState<AspectCounts>(ZERO_COUNTS);
  const [rows, setRows] = useState<TestPatientRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [buildOpen, setBuildOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);

  const fetchAll = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      listTestPatients({ aspect }),
      getAspectCounts(),
    ])
      .then(([patientRows, aspectCounts]) => {
        setRows(patientRows);
        setCounts(aspectCounts);
      })
      .catch((exc: unknown) => {
        setError(
          exc instanceof Error
            ? exc.message
            : "Could not load the test patient library.",
        );
      })
      .finally(() => setLoading(false));
  }, [aspect]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll, refreshKey]);

  const handleDelete = useCallback(async (row: TestPatientRow) => {
    const ok = window.confirm(
      `Delete test patient "${row.name}"? This cannot be undone.`,
    );
    if (!ok) return;
    try {
      await deleteTestPatient(row.id);
      setRefreshKey((n) => n + 1);
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not delete that test patient.",
      );
    }
  }, []);

  const stats = useMemo(() => buildStats(counts), [counts]);

  const filterTabs = useMemo(
    () =>
      ASPECT_VALUES.map((value) => ({
        id: value,
        label: ASPECT_LABEL[value],
        count: counts[value as keyof AspectCounts] ?? 0,
      })),
    [counts],
  );

  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "build-patient",
        label: "Build a patient",
        icon: <AddIcon fontSize="small" />,
        variant: "secondary",
        onClick: () => setBuildOpen(true),
      },
      {
        id: "copy-from-real",
        label: "Copy from a real patient",
        icon: <FileCopyOutlinedIcon fontSize="small" />,
        variant: "primary",
        onClick: () => setCopyOpen(true),
      },
    ],
    [],
  );

  const columns: DataGridColumn<TestPatientRow>[] = useMemo(
    () => [
      {
        id: "name",
        header: "Name",
        render: (row) => (
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {row.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.id}
            </Typography>
          </Box>
        ),
      },
      {
        id: "aspect",
        header: "Part of AI",
        render: (row) => (
          <Chip
            size="small"
            label={ASPECT_LABEL[row.aspect]}
            color={row.aspect === "guidelines" ? "primary" : "default"}
            variant="outlined"
            sx={{ fontWeight: 500 }}
          />
        ),
        width: "180px",
      },
      {
        id: "source",
        header: "Source",
        render: (row) => (
          <Chip
            size="small"
            label={sourceChipLabel(row)}
            variant="outlined"
            sx={{ fontWeight: 500 }}
          />
        ),
        width: "180px",
      },
      {
        id: "demographics",
        header: "Age / sex",
        render: (row) => (
          <Typography variant="body2">{ageSex(row)}</Typography>
        ),
        width: "120px",
      },
      {
        id: "created_by",
        header: "Built by",
        render: (row) => (
          <Typography variant="body2">{row.created_by || "-"}</Typography>
        ),
        width: "160px",
      },
      {
        id: "actions",
        header: "",
        align: "right",
        width: "72px",
        render: (row) => (
          <Tooltip title={`Delete ${row.name}`} arrow>
            <span>
              <IconButton
                size="small"
                onClick={() => handleDelete(row)}
                aria-label={`Delete test patient ${row.name}`}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        ),
      },
    ],
    [handleDelete],
  );

  const emptyState = (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        No test patients saved for this view yet.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Build one or copy a real patient to get started. Test patients
        always carry the test_ prefix so they cannot leak into clinical
        screens.
      </Typography>
    </Box>
  );

  return (
    <Box>
      <StatHero stats={stats} />

      {error ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={() => setError(null)}
        >
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
          value={aspect}
          onChange={(id) => setAspect(id as AspectFilter)}
          aria-label="Filter test patients by AI aspect"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {loading ? (
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 1 }}
          >
            Loading test patients...
          </Typography>
        </Stack>
      ) : (
        <DataGridCard<TestPatientRow>
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          emptyState={emptyState}
        />
      )}

      <BuildPatientDialog
        open={buildOpen}
        initialAspect={aspect}
        onClose={() => setBuildOpen(false)}
        onCreated={() => setRefreshKey((n) => n + 1)}
      />

      <CopyFromRealDialog
        open={copyOpen}
        initialAspect={aspect}
        onClose={() => setCopyOpen(false)}
        onCloned={() => setRefreshKey((n) => n + 1)}
      />
    </Box>
  );
}
