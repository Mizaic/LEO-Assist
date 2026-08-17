/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

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
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type DataGridColumn,
  type ToolbarAction,
} from "@leo/design-system";

import type { LabResultConfigSummary } from "./types";
import AddObservableDialog from "./AddObservableDialog";
import ObservableDetailPanel from "./ObservableDetailPanel";
import { useLabResultsList, type LabResultsList } from "./useLabResultsList";

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
  const page = useLabResultsList();
  return (
    <Stack spacing={2}>
      <StatHero stats={page.stats} />
      {page.error ? (
        <Alert severity="error" onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <LabsChrome page={page} />
      <SpringSwap swapKey={page.query || "all"}>
        <LabsWorkspace page={page} />
      </SpringSwap>
      {page.addOpen ? (
        <AddObservableDialog
          onClose={() => page.setAddOpen(false)}
          onCreated={page.onCreated}
        />
      ) : null}
      <Snackbar
        open={page.toast !== null}
        autoHideDuration={4000}
        onClose={() => page.setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="success" onClose={() => page.setToast(null)} sx={{ width: "100%" }}>
          {page.toast}
        </Alert>
      </Snackbar>
    </Stack>
  );
}

function LabsChrome({ page }: { page: LabResultsList }) {
  const toolbarActions: ToolbarAction[] = [
    {
      id: "add-observable",
      label: "Add observable",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => page.setAddOpen(true),
    },
  ];
  return (
    <StickyChrome testId="results-labs-chrome">
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
          search={page.query}
          onSearchChange={page.setQuery}
          searchPlaceholder="Search observables by name or SNOMED code..."
          aria-label="Filter observables"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>
    </StickyChrome>
  );
}

function LabsWorkspace({ page }: { page: LabResultsList }) {
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <DataGridCard
          columns={COLUMNS}
          rows={page.items}
          rowKey={(row) => row.concept_id}
          onRowClick={page.handleRowClick}
          dense
          emptyState={page.emptyState}
        />
      </Box>
      {page.selected ? (
        <ObservableDetailPanel
          config={page.selected}
          onRefresh={page.refreshSelected}
          onClose={() => page.setSelected(null)}
          onToast={page.setToast}
        />
      ) : null}
    </Box>
  );
}
