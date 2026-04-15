"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import PersonaLensToggle from "./PersonaLensToggle";
import MissionCardGrid from "./MissionCardGrid";
import ScopingWizard from "./ScopingWizard";
import ResultsPanel from "./ResultsPanel";
import { useResearchState } from "./useResearchState";

export default function PathwayExplorerWorkspace() {
  const state = useResearchState();

  const showResultsPanel =
    !!state.activeMission && !state.scopingOpen;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      }}
    >
      {/* Page header */}
      <Box
        sx={{
          px: 3,
          pt: 3,
          pb: 2,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          flexShrink: 0,
        }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Pathway Explorer
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          What do you want to find out? Choose an investigation below.
        </Typography>
        <PersonaLensToggle value={state.lens} onChange={state.setLens} />
      </Box>

      {/* Body: split into card grid + optional results panel */}
      <Box
        sx={{
          display: "flex",
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/* Mission card grid */}
        <Box
          sx={{
            flex: showResultsPanel ? "0 0 55%" : "1",
            overflowY: "auto",
          }}
          aria-label="Available investigations"
        >
          <MissionCardGrid
            catalogue={state.catalogue}
            loading={state.catalogueLoading}
            error={state.catalogueError}
            lens={state.lens}
            onSelect={state.selectMission}
          />
        </Box>

        {/* Results panel */}
        {showResultsPanel && (
          <>
            <Divider orientation="vertical" flexItem />
            <Box
              sx={{
                flex: "0 0 45%",
                overflowY: "auto",
              }}
              aria-label="Investigation results"
            >
              <ResultsPanel
                mission={state.activeMission}
                lens={state.lens}
                run={state.activeRun}
                result={state.result}
                loading={state.runLoading}
                onClose={state.closeMission}
                onAdjustScope={state.openScoping}
                onNavigate={state.navigateToMission}
              />
            </Box>
          </>
        )}
      </Box>

      {/* Scoping wizard dialog */}
      <ScopingWizard
        open={state.scopingOpen}
        mission={state.activeMission}
        lens={state.lens}
        scoping={state.scoping}
        onClose={state.closeScoping}
        onUpdate={state.updateScoping}
        onSubmit={state.submitRun}
      />
    </Box>
  );
}
