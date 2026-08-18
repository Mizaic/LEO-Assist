/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";

interface Props {
  chunkCount: number;
  size?: "small" | "medium";
}

/** Documents with pipeline chunks can be reprocessed through the referral AI. */
export function DocumentAiReadyChip({ chunkCount, size = "small" }: Props) {
  if (chunkCount <= 0) return null;

  const label = size === "small" ? "AI ready" : `AI ready (${chunkCount})`;
  const tooltip =
    chunkCount === 1
      ? "1 pipeline chunk is stored. You can reprocess this document."
      : `${chunkCount} pipeline chunks are stored. You can reprocess this document.`;

  return (
    <Tooltip title={tooltip}>
      <Chip
        label={label}
        size="small"
        data-testid="document-ai-ready-chip"
        sx={{
          height: size === "small" ? 18 : 22,
          fontSize: size === "small" ? 10 : 11,
          fontWeight: 600,
          bgcolor: "#ECFDF5",
          color: "#047857",
          border: "1px solid #A7F3D0",
        }}
      />
    </Tooltip>
  );
}

export function documentHasPipelineChunks(doc: { chunk_count?: number }): boolean {
  return Number(doc.chunk_count || 0) > 0;
}
