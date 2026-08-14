/**
 * Facts and codes that arrived for a Validation Lab pipeline stage.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883
 *   VT: VT-825F42CC
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { LabWorkItem, LabWorkPreview } from "../inspectorTypes";
import { markBackground, markForeground } from "../letterMarkStyle";
import { EvidenceTooltip } from "./EvidenceTooltip";

const DIFF_MOTION = {
  "@keyframes leoChipNew": {
    from: { opacity: 0, transform: "scale(0.88)" },
    to: { opacity: 1, transform: "scale(1)" },
  },
  "@keyframes leoChipPulseAmber": {
    "0%, 100%": { boxShadow: "none" },
    "50%": { boxShadow: "0 0 6px 3px rgba(217,119,6,0.38)" },
  },
  "@keyframes leoChipPulseRed": {
    "0%, 100%": { boxShadow: "none" },
    "50%": { boxShadow: "0 0 6px 3px rgba(220,38,38,0.38)" },
  },
} as const;

function chipChangeSx(change?: string): Record<string, unknown> {
  if (change === "new") {
    return { borderColor: "#059669", borderWidth: 2, animation: "leoChipNew 0.35s ease-out" };
  }
  if (change === "dropped") {
    return { textDecoration: "line-through", opacity: 0.45, borderColor: "#94A3B8" };
  }
  if (change === "context") {
    return { borderColor: "#D97706", borderWidth: 2, animation: "leoChipPulseAmber 1.4s ease-in-out infinite" };
  }
  if (change === "uncoded") {
    return { borderColor: "#DC2626", borderWidth: 2, animation: "leoChipPulseRed 1.1s ease-in-out infinite" };
  }
  if (change === "coded") return { borderColor: "#2563EB", borderWidth: 2 };
  if (change === "measured") return { borderColor: "#0891B2", borderWidth: 2 };
  if (change === "kind") return { borderColor: "#7C3AED", borderWidth: 2 };
  return {};
}

function DiffBadge({ items }: { items: LabWorkItem[] }) {
  const added = items.filter((i) => i.change === "new").length;
  const dropped = items.filter((i) => i.change === "dropped").length;
  if (!added && !dropped) return null;
  return (
    <Typography
      variant="caption"
      sx={{ display: "block", mb: 0.5, fontWeight: 600, letterSpacing: "0.02em" }}
      data-testid="validation-lab-diff-badge"
    >
      {added ? (
        <Box component="span" sx={{ color: "#059669", mr: dropped ? 1 : 0 }}>
          +{added} new
        </Box>
      ) : null}
      {dropped ? (
        <Box component="span" sx={{ color: "#DC2626" }}>
          -{dropped} dropped
        </Box>
      ) : null}
    </Typography>
  );
}

function itemLabel(item: LabWorkItem): string {
  if (item.kind === "relation" && item.relationTarget) {
    return `${item.text} -- ${item.relationType} -- ${item.relationTarget}`;
  }
  const measurement = [item.value, item.unit].filter(Boolean).join(" ");
  if (measurement) return `${item.text} -- ${measurement}`;
  if (item.code) return `${item.text} -- ${item.code}`;
  return item.text;
}

interface Props {
  preview: LabWorkPreview | null;
  loading: boolean;
  onMarkWrong?: (text: string) => void;
}

export function StageWorkPreview({ preview, loading, onMarkWrong }: Props) {
  if (loading) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Loading what this step found...
      </Typography>
    );
  }
  const items = preview?.items || [];
  const headline = preview?.headline || "";
  if (!headline && !items.length) return null;
  const hasDiff = items.some((i) => i.change && i.change !== "stable");
  return (
    <Box
      data-testid="validation-lab-stage-work"
      sx={{
        mb: 1.5,
        p: 1.25,
        bgcolor: "#F0FDF4",
        border: "1px solid #BBF7D0",
        borderRadius: "8px",
        ...(hasDiff ? DIFF_MOTION : {}),
      }}
    >
      {headline ? (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            fontWeight: 700,
            color: "#166534",
            mb: items.length ? 0.75 : 0,
          }}
        >
          {headline}
        </Typography>
      ) : null}
      {hasDiff ? <DiffBadge items={items} /> : null}
      {items.length ? (
        <Stack
          direction="row"
          flexWrap="wrap"
          gap={0.75}
          sx={{ maxHeight: 220, overflowY: "auto", pr: 0.5 }}
        >
          {items.map((item, index) => (
            <EvidenceTooltip key={`${item.text}-${index}`} item={item}>
              <Chip
                size="small"
                label={itemLabel(item)}
                data-change={item.change || "stable"}
                onClick={onMarkWrong ? () => onMarkWrong(item.text) : undefined}
                sx={{
                  height: 22,
                  fontSize: "0.7rem",
                  maxWidth: "100%",
                  background: item.kind === "relation"
                    ? "#F1F5F9"
                    : item.kind === "inferred"
                      ? "#F8FAFC"
                      : markBackground(item.assertion, item.semanticTag),
                  color: item.kind === "relation" || item.kind === "inferred"
                    ? "#334155"
                    : markForeground(item.assertion, item.semanticTag),
                  border: item.kind === "inferred"
                    ? "1px dashed #94A3B8"
                    : item.kind === "relation"
                      ? "1px solid #94A3B8"
                      : "1px solid #CBD5E1",
                  fontStyle: item.kind === "relation" ? "italic" : "normal",
                  ...chipChangeSx(item.change),
                }}
              />
            </EvidenceTooltip>
          ))}
        </Stack>
      ) : null}
    </Box>
  );
}
