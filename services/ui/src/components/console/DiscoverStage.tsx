"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import RunSection from "@/components/operations/RunSection";
import { FONT_SIZES } from "@/theme/tokens";

interface DiscoverStageProps {
  onAction?: () => void;
}

export function DiscoverStage({ onAction }: DiscoverStageProps) {
  return (
    <Box sx={{ pt: 2 }}>
      <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary", mb: 2 }}>
        Encounters processed through the NER pipeline arrive here as training
        candidates. Run the pipeline to extract new clinical entities from
        today&apos;s encounters.
      </Typography>
      <RunSection />
    </Box>
  );
}
