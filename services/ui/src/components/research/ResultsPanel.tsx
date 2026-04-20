/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   DI: DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import type { MissionDescription, MissionRun, PersonaLens, RunResult } from "@/lib/researchApi";
import HeadlineResult from "./HeadlineResult";
import ResultsTable from "./ResultsTable";
import MethodExplainer from "./MethodExplainer";
import GuidedNextSteps from "./GuidedNextSteps";

interface Props {
  mission: MissionDescription | null;
  lens: PersonaLens;
  run: MissionRun | null;
  result: RunResult | null;
  loading: boolean;
  onClose: () => void;
  onAdjustScope: () => void;
  onNavigate: (missionId: string) => void;
}

export default function ResultsPanel({
  mission,
  lens,
  run,
  result,
  loading,
  onClose,
  onAdjustScope,
  onNavigate,
}: Props) {
  const [tab, setTab] = useState(0);

  if (!mission) return null;

  const title = mission.titles[lens] ?? mission.titles.patients;
  const hasResults = !!result && result.data_available && !result.error;
  const hasError =
    run?.status === "failed" || (result && (!!result.error || !result.data_available));

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        bgcolor: "background.paper",
        borderLeft: "1px solid",
        borderColor: "divider",
      }}
    >
      {/* Panel header */}
      <Box
        sx={{
          px: 3,
          py: 2,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "flex-start",
          gap: 1,
        }}
      >
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
            {title}
          </Typography>
        </Box>
        <Tooltip title="Adjust scope">
          <IconButton
            size="small"
            onClick={onAdjustScope}
            aria-label="Adjust investigation scope"
          >
            <TuneOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Close">
          <IconButton
            size="small"
            onClick={onClose}
            aria-label="Close results panel"
          >
            <CloseOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Headline layer -- always visible */}
      <Box sx={{ px: 3, py: 2 }}>
        <HeadlineResult
          result={result}
          loading={loading}
          error={result?.error}
        />
      </Box>

      {/* Tab bar: Visual (placeholder) | Data | Method */}
      {hasResults && (
        <>
          <Box sx={{ px: 3, borderBottom: "1px solid", borderColor: "divider" }}>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab
                label="Data"
                sx={{ textTransform: "none", fontSize: "0.875rem" }}
              />
              <Tab
                label="Method"
                sx={{ textTransform: "none", fontSize: "0.875rem" }}
              />
            </Tabs>
          </Box>

          <Box sx={{ flex: 1, overflowY: "auto", px: 3, py: 2 }}>
            {tab === 0 && (
              <>
                <ResultsTable result={result} runId={run?.run_id} />
                <GuidedNextSteps result={result} onNavigate={onNavigate} />
              </>
            )}
            {tab === 1 && <MethodExplainer result={result} />}
          </Box>
        </>
      )}

      {hasError && !loading && (
        <Box sx={{ px: 3, py: 1 }}>
          <Button
            size="small"
            variant="outlined"
            onClick={onAdjustScope}
            sx={{ textTransform: "none" }}
          >
            Try different settings
          </Button>
        </Box>
      )}
    </Box>
  );
}
