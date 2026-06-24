"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 * Drag/drop tile grid using react-grid-layout v3.
 */

import { useMemo } from "react";
import { GridLayout, type Layout, type LayoutItem } from "react-grid-layout";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import NumbersIcon from "@mui/icons-material/Numbers";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import TimelineIcon from "@mui/icons-material/Timeline";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { type AuditTile, type TileType } from "@/lib/auditTemplateApi";

const TILE_ICONS: Record<TileType, React.ElementType> = {
  bar_chart: BarChartIcon,
  line_chart: ShowChartIcon,
  kpi_strip: NumbersIcon,
  table: TableChartOutlinedIcon,
  interval_plot: TimelineIcon,
  text: TextFieldsIcon,
};

interface TileGridProps {
  tiles: AuditTile[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
  onLayoutChange: (tiles: AuditTile[]) => void;
  onOpenAssistant?: () => void;
}

function tileToLayoutItem(t: AuditTile): LayoutItem {
  const l = t.layout ?? { x: 0, y: 0, w: 4, h: 2 };
  return { i: t.tile_id, x: l.x, y: l.y, w: l.w, h: l.h };
}

export default function TileGrid({
  tiles,
  selectedId,
  onSelect,
  onRemove,
  onLayoutChange,
  onOpenAssistant,
}: TileGridProps) {
  const layout: LayoutItem[] = useMemo(() => tiles.map(tileToLayoutItem), [tiles]);

  const handleLayoutChange = (newLayout: Layout) => {
    const updated = tiles.map((t) => {
      const l = newLayout.find((nl: LayoutItem) => nl.i === t.tile_id);
      return l ? { ...t, layout: { x: l.x, y: l.y, w: l.w, h: l.h } } : t;
    });
    onLayoutChange(updated);
  };

  if (tiles.length === 0) {
    return (
      <Box
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 2,
          border: "2px dashed",
          borderColor: "divider",
          borderRadius: 2,
          color: "text.disabled",
          p: 4,
        }}
      >
        <Typography variant="body2" textAlign="center">
          No tiles yet. Add from the library on the left, or click{" "}
          <strong>AI</strong> to describe the dashboard you need.
        </Typography>
        {onOpenAssistant && (
          <Button
            size="small"
            variant="outlined"
            startIcon={<AutoAwesomeOutlinedIcon />}
            onClick={onOpenAssistant}
          >
            AI
          </Button>
        )}
      </Box>
    );
  }

  return (
    <GridLayout
      width={900}
      layout={layout}
      onLayoutChange={handleLayoutChange}
      gridConfig={{ cols: 12, rowHeight: 80 }}
      style={{ minHeight: 400 }}
    >
      {tiles.map((tile) => {
        const Icon = TILE_ICONS[tile.tile_type] ?? BarChartIcon;
        const isSelected = tile.tile_id === selectedId;
        return (
          <Box
            key={tile.tile_id}
            onClick={() => onSelect(tile.tile_id)}
            sx={{
              border: "2px solid",
              borderColor: isSelected ? "primary.main" : "divider",
              borderRadius: 1.5,
              bgcolor: "background.paper",
              overflow: "hidden",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Box
              data-grid-drag-handle
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                px: 1,
                py: 0.5,
                bgcolor: isSelected ? "primary.50" : "grey.50",
                borderBottom: "1px solid",
                borderColor: "divider",
                cursor: "grab",
                gap: 1,
              }}
            >
              <Icon sx={{ fontSize: 14, color: "text.secondary" }} />
              <Typography variant="caption" fontWeight={600} flex={1} noWrap>
                {tile.label}
              </Typography>
              <Tooltip title="Remove tile">
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(tile.tile_id);
                  }}
                  sx={{ p: 0.25 }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </Box>
            <Box
              sx={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "text.disabled",
              }}
            >
              <Typography variant="caption">{tile.tile_type}</Typography>
            </Box>
          </Box>
        );
      })}
    </GridLayout>
  );
}
