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

import { SegmentedTabs, type SegmentedTab } from "@leo/design-system";

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
    <Box
      sx={{
        width: 500,
        flexShrink: 0,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "12px",
        bgcolor: "background.paper",
        overflow: "hidden",
        alignSelf: "flex-start",
        position: "sticky",
        top: 16,
        maxHeight: "calc(100vh - 200px)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Stack
        direction="row"
        alignItems="flex-start"
        justifyContent="space-between"
        sx={{
          p: 2,
          pb: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack spacing={0.75}>
          <Typography variant="h6" component="h2">
            {config.display_name}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Chip label={config.concept_id} size="small" />
            {config.canonical_unit && (
              <Chip label={config.canonical_unit} size="small" variant="outlined" />
            )}
          </Stack>
        </Stack>
        <IconButton
          size="small"
          aria-label="Close detail panel"
          onClick={onClose}
          sx={{ mt: -0.5 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>

      <Box
        sx={{
          px: 2,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <SegmentedTabs
          tabs={tabs}
          value={activeTab}
          onChange={setActiveTab}
          aria-label="Observable detail sections"
          dense
        />
      </Box>

      <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
        {activeTab === "conversions" && (
          <ConversionsTab
            conceptId={config.concept_id}
            conversions={config.conversions}
            onRefresh={onRefresh}
            onToast={onToast}
          />
        )}
        {activeTab === "ranges" && (
          <RangesTab
            conceptId={config.concept_id}
            ranges={config.ranges}
            onRefresh={onRefresh}
            onToast={onToast}
          />
        )}
        {activeTab === "interpretations" && (
          <InterpretationsTab
            conceptId={config.concept_id}
            interpretations={config.interpretations}
            onRefresh={onRefresh}
            onToast={onToast}
          />
        )}
      </Box>
    </Box>
  );
}
