/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { SegmentedTabs, SpringSwap, type SegmentedTab } from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import type { LabResultConfig } from "./types";
import ConversionsTab from "./ConversionsTab";
import InterpretationsTab from "./InterpretationsTab";
import RangesTab from "./RangesTab";

const BASE_TABS: SegmentedTab[] = [
  { id: "conversions", label: "Unit conversions" },
  { id: "ranges", label: "Reference ranges" },
  { id: "interpretations", label: "Interpretations" },
];

interface Props {
  config: LabResultConfig;
  onRefresh: () => Promise<void>;
  onClose: () => void;
  onToast: (msg: string) => void;
}

export default function ObservableDetailPanel({
  config,
  onRefresh,
  onClose,
  onToast,
}: Props) {
  const [activeTab, setActiveTab] = useState("conversions");

  const tabs: SegmentedTab[] = BASE_TABS.map((t) => ({
    ...t,
    count:
      t.id === "conversions"
        ? config.conversions.length
        : t.id === "ranges"
          ? config.ranges.length
          : config.interpretations.length,
  }));

  return (
    <Box sx={detailShellSx}>
      <DetailHeader config={config} onClose={onClose} />
      <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid " + color.surface.divider }}>
        <SegmentedTabs
          tabs={tabs}
          value={activeTab}
          onChange={setActiveTab}
          aria-label="Observable detail sections"
          dense
        />
      </Box>
      <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
        <SpringSwap swapKey={activeTab}>
          <DetailBody
            activeTab={activeTab}
            config={config}
            onRefresh={onRefresh}
            onToast={onToast}
          />
        </SpringSwap>
      </Box>
    </Box>
  );
}

function DetailHeader({
  config,
  onClose,
}: {
  config: LabResultConfig;
  onClose: () => void;
}) {
  return (
    <Stack
      direction="row"
      alignItems="flex-start"
      justifyContent="space-between"
      sx={{ p: 2, pb: 1.5, borderBottom: "1px solid " + color.surface.divider }}
    >
      <Stack spacing={0.75}>
        <Typography
          variant="h6"
          component="h2"
          sx={{
            fontFamily: typography.fontFamily.heading,
            fontWeight: 700,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
          }}
        >
          {config.display_name}
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Chip label={config.concept_id} size="small" />
          {config.canonical_unit ? (
            <Chip label={config.canonical_unit} size="small" variant="outlined" />
          ) : null}
        </Stack>
      </Stack>
      <IconButton size="small" aria-label="Close detail panel" onClick={onClose} sx={{ mt: -0.5 }}>
        <CloseIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}

function DetailBody({
  activeTab,
  config,
  onRefresh,
  onToast,
}: {
  activeTab: string;
  config: LabResultConfig;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  if (activeTab === "conversions") {
    return (
      <ConversionsTab
        conceptId={config.concept_id}
        conversions={config.conversions}
        onRefresh={onRefresh}
        onToast={onToast}
      />
    );
  }
  if (activeTab === "ranges") {
    return (
      <RangesTab
        conceptId={config.concept_id}
        ranges={config.ranges}
        onRefresh={onRefresh}
        onToast={onToast}
      />
    );
  }
  return (
    <InterpretationsTab
      conceptId={config.concept_id}
      displayName={config.display_name}
      interpretations={config.interpretations}
      onRefresh={onRefresh}
      onToast={onToast}
    />
  );
}

const detailShellSx = {
  width: 520,
  flexShrink: 0,
  border: "1px solid " + color.text.secondary,
  borderRadius: "12px",
  bgcolor: color.surface.raised,
  boxShadow: elevation.card,
  overflow: "hidden",
  alignSelf: "flex-start",
  position: "sticky",
  top: 16,
  maxHeight: "calc(100vh - 200px)",
  display: "flex",
  flexDirection: "column",
};
