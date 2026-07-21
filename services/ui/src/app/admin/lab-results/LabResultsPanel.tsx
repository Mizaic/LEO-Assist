/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";

import {
  DataGridCard,
  FilterBar,
  StatHero,
  ToolbarActions,
  type DataGridColumn,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import { getLabResultConfig, listLabResultConfigs } from "./api";
import type { LabResultConfig, LabResultConfigSummary } from "./types";
import AddObservableDialog from "./AddObservableDialog";
import ObservableDetailPanel from "./ObservableDetailPanel";

const COLUMNS: DataGridColumn<LabResultConfigSummary>[] = [
  {
    id: "name",
    header: "Observable",
    render: (row) => (
      <Typography variant="body2" fontWeight={500}>
        {row.display_name}
      </Typography>
    ),
  },
  {
    id: "snomed",
    header: "SNOMED",
    render: (row) => <Chip label={row.concept_id} size="small" />,
  },
  {
    id: "unit",
    header: "Canonical unit",
    render: (row) => (
      <Typography variant="body2" color="text.secondary">
        {row.canonical_unit || "-"}
      </Typography>
    ),
  },
  {
    id: "ranges",
    header: "Ranges",
    align: "right",
    render: (row) => (
      <Chip
        label={row.range_count ?? 0}
        size="small"
        color={(row.range_count ?? 0) === 0 ? "warning" : "default"}
        variant={(row.range_count ?? 0) === 0 ? "outlined" : "filled"}
      />
    ),
  },
  {
    id: "conversions",
    header: "Conversions",
    align: "right",
    render: (row) => (
      <Chip label={row.conversion_count ?? 0} size="small" variant="outlined" />
    ),
  },
];

export default function LabResultsPanel() {
  const [allItems, setAllItems] = useState<LabResultConfigSummary[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<LabResultConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLabResultConfigs("");
      setAllItems(data.items || []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load lab configs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const items = useMemo(() => {
    if (!query.trim()) return allItems;
    const q = query.toLowerCase();
    return allItems.filter(
      (i) =>
        i.display_name.toLowerCase().includes(q) ||
        i.concept_id.toLowerCase().includes(q),
    );
  }, [allItems, query]);

  const handleRowClick = useCallback(async (row: LabResultConfigSummary) => {
    setError(null);
    try {
      const data = await getLabResultConfig(row.concept_id);
      setSelected(data.item);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load config.");
    }
  }, []);

  const refreshSelected = useCallback(async () => {
    if (selected) {
      const data = await getLabResultConfig(selected.concept_id);
      setSelected(data.item);
    }
    await loadList();
  }, [selected, loadList]);

  const stats = useMemo<StatTile[]>(
    () => [
      {
        id: "total",
        label: "Configured observables",
        value: allItems.length,
      },
      {
        id: "no-ranges",
        label: "Missing ranges",
        value: allItems.filter((i) => !(i.range_count ?? 0)).length,
        tone: allItems.some((i) => !(i.range_count ?? 0)) ? "warning" : "positive",
      },
      {
        id: "no-conversions",
        label: "Missing conversions",
        value: allItems.filter((i) => !(i.conversion_count ?? 0)).length,
        tone: allItems.some((i) => !(i.conversion_count ?? 0)) ? "warning" : "positive",
      },
      {
        id: "no-interpretations",
        label: "Missing interpretations",
        value: allItems.filter((i) => !(i.interpretation_count ?? 0)).length,
        tone: allItems.some((i) => !(i.interpretation_count ?? 0)) ? "warning" : "positive",
      },
    ],
    [allItems],
  );

  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "add-observable",
        label: "Add observable",
        icon: <AddIcon fontSize="small" />,
        variant: "primary",
        onClick: () => setAddOpen(true),
      },
    ],
    [],
  );

  const emptyState =
    loading
      ? "Loading observables..."
      : query
        ? "No observables match this search."
        : "No observables configured yet. Click \"Add observable\" to create the first one.";

  return (
    <Stack spacing={2}>
      <StatHero stats={stats} />
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <FilterBar
          search={query}
          onSearchChange={setQuery}
          searchPlaceholder="Search observables by name or SNOMED code..."
          aria-label="Filter observables"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>
      <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <DataGridCard
            columns={COLUMNS}
            rows={items}
            rowKey={(row) => row.concept_id}
            onRowClick={handleRowClick}
            dense
            emptyState={emptyState}
          />
        </Box>
        {selected && (
          <ObservableDetailPanel
            config={selected}
            onRefresh={refreshSelected}
            onClose={() => setSelected(null)}
            onToast={setToast}
          />
        )}
      </Box>
      {addOpen && (
        <AddObservableDialog
          onClose={() => setAddOpen(false)}
          onCreated={async (id) => {
            setAddOpen(false);
            await loadList();
            const data = await getLabResultConfig(id);
            setSelected(data.item);
            setToast("Observable added.");
          }}
        />
      )}
      <Snackbar
        open={toast !== null}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="success" onClose={() => setToast(null)} sx={{ width: "100%" }}>
          {toast}
        </Alert>
      </Snackbar>
    </Stack>
  );
}
