"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import DeploySection from "@/components/operations/DeploySection";
import ModelLifecyclePanel from "@/components/operations/ModelLifecyclePanel";
import { FONT_SIZES } from "@/theme/tokens";

interface DeployStageProps {
  promotedVersion?: string | null;
}

export function DeployStage({ promotedVersion }: DeployStageProps) {
  return (
    <Box sx={{ pt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      {promotedVersion && (
        <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
          Live version: <strong>{promotedVersion}</strong>
        </Typography>
      )}
      <DeploySection />
      <ModelLifecyclePanel />
    </Box>
  );
}
