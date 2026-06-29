"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Left panel for the audit template builder.
 * Three tabs:
 *   Data     -- metric catalogue with category filter + search
 *   Content  -- Canva-style content blocks (text, layout, media)
 *   Templates -- one-click starter layouts
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import BarChartIcon from "@mui/icons-material/BarChart";
import ViewModuleOutlinedIcon from "@mui/icons-material/ViewModuleOutlined";
import DashboardCustomizeOutlinedIcon from "@mui/icons-material/DashboardCustomizeOutlined";
import {
  type MetricCatalogueEntry,
  type TileType,
  type WidgetCatalogueEntry,
} from "@/lib/auditTemplateApi";
import { type ContentBlockEntry } from "@/lib/contentBlocks";
import { type StarterLayout } from "./StarterLayouts";
import DataPanel from "./DataPanel";
import ContentPanel from "./ContentPanel";
import StarterLayouts from "./StarterLayouts";

export interface MetricPickerProps {
  catalogue: MetricCatalogueEntry[];
  loading: boolean;
  error: string | null;
  usedCounts: Map<string, number>;
  onAdd: (metric: MetricCatalogueEntry, tileType: TileType) => void;
  onAddWidget: (widget: WidgetCatalogueEntry) => void;
  onAddStarter: (starter: StarterLayout, catalogue: MetricCatalogueEntry[]) => void;
  onAddContent: (block: ContentBlockEntry) => void;
}

export default function MetricPicker({
  catalogue,
  loading,
  error,
  usedCounts,
  onAdd,
  onAddWidget,
  onAddStarter,
  onAddContent,
}: MetricPickerProps) {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="fullWidth"
        sx={{
          minHeight: 36,
          borderBottom: "1px solid",
          borderColor: "divider",
          "& .MuiTab-root": { minHeight: 36, fontSize: 11, fontWeight: 600, py: 0.5 },
        }}
      >
        <Tab icon={<BarChartIcon sx={{ fontSize: 13 }} />} iconPosition="start" label="Data" />
        <Tab icon={<ViewModuleOutlinedIcon sx={{ fontSize: 13 }} />} iconPosition="start" label="Content" />
        <Tab icon={<DashboardCustomizeOutlinedIcon sx={{ fontSize: 13 }} />} iconPosition="start" label="Templates" />
      </Tabs>

      <Box sx={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {tab === 0 && (
          <DataPanel
            catalogue={catalogue}
            loading={loading}
            error={error}
            usedCounts={usedCounts}
            onAdd={onAdd}
            onAddWidget={onAddWidget}
          />
        )}
        {tab === 1 && <ContentPanel onAddContent={onAddContent} />}
        {tab === 2 && (
          <Box sx={{ p: 1.5, flex: 1, overflowY: "auto" }}>
            <StarterLayouts catalogue={catalogue} onApply={onAddStarter} />
          </Box>
        )}
      </Box>
    </Box>
  );
}
