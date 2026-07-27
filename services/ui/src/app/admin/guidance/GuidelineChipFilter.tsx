/**
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

interface GuidelineChipFilterProps {
  guidelineIds: string[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export default function GuidelineChipFilter({
  guidelineIds,
  selected,
  onSelect,
}: GuidelineChipFilterProps) {
  if (guidelineIds.length < 2) return null;
  return (
    <Box sx={{ mb: 2 }}>
      <Typography
        variant="overline"
        sx={{ fontWeight: 700, letterSpacing: 0.6, display: "block", mb: 0.75 }}
      >
        Filter by guideline
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap">
        <Chip
          label="All"
          size="small"
          variant={selected === null ? "filled" : "outlined"}
          color={selected === null ? "primary" : "default"}
          onClick={() => onSelect(null)}
          sx={{ cursor: "pointer" }}
        />
        {guidelineIds.map((id) => (
          <Chip
            key={id}
            label={id}
            size="small"
            variant={selected === id ? "filled" : "outlined"}
            color={selected === id ? "primary" : "default"}
            onClick={() => onSelect(id)}
            sx={{ cursor: "pointer", fontWeight: selected === id ? 700 : 400 }}
          />
        ))}
      </Stack>
    </Box>
  );
}
