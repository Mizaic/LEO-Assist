/**
 * Validation Lab run inspector drawer shell.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import type { UseLabRunInspectorReturn } from "@/hooks/useLabRunInspector";
import { RunInspectorDataTab } from "./RunInspectorDataTab";
import { RunInspectorLogTab } from "./RunInspectorLogTab";
import { RunInspectorTraceTab } from "./RunInspectorTraceTab";

interface Props {
  open: boolean;
  onClose: () => void;
  runId: string;
  title: string;
  inspector: UseLabRunInspectorReturn;
}

export function RunInspectorDrawer({
  open,
  onClose,
  runId,
  title,
  inspector,
}: Props) {
  const [tab, setTab] = useState(0);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: { width: { xs: "100%", sm: 520 }, maxWidth: "100vw" },
      }}
      data-testid="validation-lab-run-inspector"
    >
      <Stack spacing={0} sx={{ height: "100%" }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "divider" }}
        >
          <Box>
            <Typography variant="subtitle1" fontWeight={700}>
              Run inspector
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {title} · {runId.slice(0, 8)}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              size="small"
              label={inspector.connected ? "Live" : "Polling"}
              color={inspector.connected ? "success" : "default"}
              data-testid="validation-lab-inspector-live-chip"
            />
            <IconButton aria-label="Close inspector" onClick={onClose} size="small">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="fullWidth"
          sx={{ borderBottom: 1, borderColor: "divider" }}
        >
          <Tab label="Live log" data-testid="validation-lab-inspector-tab-log" />
          <Tab label="Trace" data-testid="validation-lab-inspector-tab-trace" />
          <Tab label="Data flow" data-testid="validation-lab-inspector-tab-data" />
        </Tabs>
        <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
          {inspector.error ? (
            <Typography color="error" variant="body2" sx={{ mb: 1 }}>
              {inspector.error}
            </Typography>
          ) : null}
          {tab === 0 ? (
            <RunInspectorLogTab events={inspector.events} />
          ) : null}
          {tab === 1 ? (
            <RunInspectorTraceTab
              spans={inspector.spans}
              planSteps={inspector.snapshot?.plan_steps || []}
              selectedStepId={inspector.selectedStepId}
              onSelectStep={inspector.setSelectedStepId}
            />
          ) : null}
          {tab === 2 ? (
            <RunInspectorDataTab
              spans={inspector.spans}
              selectedStepId={inspector.selectedStepId}
              onSelectStep={inspector.setSelectedStepId}
              stageDetail={inspector.stageDetail}
              loading={inspector.stageLoading}
            />
          ) : null}
        </Box>
      </Stack>
    </Drawer>
  );
}
