"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import GoldDatasetPanel from "@/components/gold-dataset/GoldDatasetPanel";
import { FONT_SIZES } from "@/theme/tokens";

interface CurateStageProps {
  queueTotal?: number | null;
}

export function CurateStage({ queueTotal }: CurateStageProps) {
  return (
    <Box sx={{ pt: 2 }}>
      <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary", mb: 2 }}>
        Review training candidates to build a high-quality gold dataset.
        {queueTotal != null && queueTotal > 0 && (
          <Box component="span" sx={{ fontWeight: 700, color: "warning.main" }}>
            {" "}{queueTotal} candidates waiting — sorted by how much each would teach the model.
          </Box>
        )}
      </Typography>
      <GoldDatasetPanel />
    </Box>
  );
}
