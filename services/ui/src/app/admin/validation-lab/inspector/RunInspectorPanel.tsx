/**
 * Validation Lab run inspector panel (embedded in run sheet modal).
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";

import type { UseLabRunInspectorReturn } from "@/hooks/useLabRunInspector";
import { RunInspectorDataTab } from "./RunInspectorDataTab";
import { RunInspectorLogTab } from "./RunInspectorLogTab";
import { RunInspectorSummaryTab } from "./RunInspectorSummaryTab";

interface Props {
  runId: string;
  runStatus: string;
  terminal: boolean;
  inspector: UseLabRunInspectorReturn;
}

export function RunInspectorPanel({
  runId,
  runStatus,
  terminal,
  inspector,
}: Props) {
  const [tab, setTab] = useState(0);
  const liveLabel = inspector.connected
    ? "Live"
    : terminal
      ? "Completed"
      : "Polling";

  return (
    <Stack
      spacing={1.5}
      sx={{ mt: 1 }}
      data-testid="validation-lab-run-inspector"
    >
      <Divider />
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" fontWeight={700}>
          Run inspector
        </Typography>
        <Chip
          size="small"
          label={liveLabel}
          color={inspector.connected ? "success" : "default"}
          data-testid="validation-lab-inspector-live-chip"
        />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        {runId.slice(0, 8)} · {runStatus}
      </Typography>
      <Tabs
        value={tab}
        onChange={(_, value) => setTab(value)}
        variant="fullWidth"
        sx={{ borderBottom: 1, borderColor: "divider" }}
      >
        <Tab label="Live log" data-testid="validation-lab-inspector-tab-log" />
        <Tab label="Data flow" data-testid="validation-lab-inspector-tab-data" />
        <Tab label="Summary" data-testid="validation-lab-inspector-tab-summary" />
      </Tabs>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          minHeight: 360,
          maxHeight: "min(68vh, 720px)",
          overflow: "hidden",
        }}
      >
        {inspector.error ? (
          <Typography color="error" variant="body2" sx={{ mb: 1 }}>
            {inspector.error}
          </Typography>
        ) : null}
        {tab === 0 ? (
          <RunInspectorLogTab
            events={inspector.events}
            terminal={terminal}
            runStatus={runStatus}
          />
        ) : null}
        {tab === 1 ? (
          <RunInspectorDataTab
            spans={inspector.spans}
            planSteps={inspector.snapshot?.plan_steps || []}
            planEdges={inspector.snapshot?.plan_edges}
            selectedStepId={inspector.selectedStepId}
            onSelectStep={inspector.setSelectedStepId}
            stageDetail={inspector.stageDetail}
            loading={inspector.stageLoading}
          />
        ) : null}
        {tab === 2 ? (
          <RunInspectorSummaryTab
            spans={inspector.spans}
            planSteps={inspector.snapshot?.plan_steps || []}
            selectedStepId={inspector.selectedStepId}
            onSelectStep={inspector.setSelectedStepId}
            stageDetail={inspector.stageDetail}
            loading={inspector.stageLoading}
          />
        ) : null}
      </Box>
    </Stack>
  );
}
