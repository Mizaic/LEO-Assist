/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0998FAF5
 *   Also implements: DO-E32DAC8D
 *   DI: DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
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
          Live AI version: <strong>{promotedVersion}</strong>
        </Typography>
      )}
      <ModelLifecyclePanel />
    </Box>
  );
}
