"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 * Drag/drop tile grid using react-grid-layout v2.
 *
 * Width is measured from the actual DOM container via useContainerWidth so
 * drag coordinates are never offset. The chart-type popover lets the user
 * change tile type inline without opening the config panel.
 */

import { useMemo, useState } from "react";
import { GridLayout, useContainerWidth, type Layout, type LayoutItem } from "react-grid-layout";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import NumbersIcon from "@mui/icons-material/Numbers";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import TimelineIcon from "@mui/icons-material/Timeline";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { type AuditTile, type TileType } from "@/lib/auditTemplateApi";

const TILE_META: Record<TileType, { Icon: React.ElementType; colour: string; label: string }> = {
  bar_chart:     { Icon: BarChartIcon,             colour: "#1E40AF", label: "Bar chart" },
  line_chart:    { Icon: ShowChartIcon,            colour: "#047857", label: "Line chart" },
  kpi_strip:     { Icon: NumbersIcon,              colour: "#7C3AED", label: "KPI strip" },
  table:         { Icon: TableChartOutlinedIcon,   colour: "#0E7490", label: "Table" },
  interval_plot: { Icon: TimelineIcon,             colour: "#B45309", label: "Interval plot" },
  text:          { Icon: TextFieldsIcon,           colour: "#475569", label: "Text" },
  widget:        { Icon: WidgetsOutlinedIcon,      colour: "#92400E", label: "Widget" },
};

// Chart types shown in the inline popover (widgets are fixed -- excluded).
const CHART_TYPES: TileType[] = [
  "bar_chart", "line_chart", "kpi_strip", "table", "interval_plot", "text",
];

interface TileGridProps {
  tiles: AuditTile[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
  onTypeChange: (tileId: string, newType: TileType) => void;
  onLayoutChange: (tiles: AuditTile[]) => void;
  onOpenAssistant?: () => void;
}

function tileToLayoutItem(t: AuditTile): LayoutItem {
  const l = t.layout ?? { x: 0, y: 0, w: 4, h: 2 };
  return { i: t.tile_id, x: l.x, y: l.y, w: l.w, h: l.h };
}

function TilePreviewBody({ type }: { type: TileType }) {
  const { colour } = TILE_META[type] ?? TILE_META.bar_chart;

  if (type === "kpi_strip") {
    return (
      <Box sx={{ display: "flex", gap: 1, px: 1.5, pb: 1, pt: 0.5 }}>
        {[48, 38, 56].map((w, i) => (
          <Box
            key={i}
            sx={{
              flex: 1,
              height: 36,
              borderRadius: 1,
              bgcolor: `${colour}14`,
              border: `1px solid ${colour}30`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Box sx={{ width: w, height: 10, borderRadius: 0.5, bgcolor: `${colour}50` }} />
          </Box>
        ))}
      </Box>
    );
  }

  if (type === "table") {
    return (
      <Box sx={{ px: 1.5, pb: 1, pt: 0.5, display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Box sx={{ height: 8, borderRadius: 0.5, bgcolor: `${colour}30`, width: "100%" }} />
        {[0, 1, 2].map((i) => (
          <Box key={i} sx={{ height: 6, borderRadius: 0.5, bgcolor: `${colour}15`, width: `${85 - i * 10}%` }} />
        ))}
      </Box>
    );
  }

  if (type === "line_chart") {
    return (
      <Box sx={{ px: 1.5, pb: 1, pt: 0.5 }}>
        <svg width="100%" height={44} viewBox="0 0 120 44" preserveAspectRatio="none">
          <polyline
            points="0,36 20,28 40,32 60,14 80,20 100,10 120,16"
            fill="none"
            stroke={colour}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.7}
          />
          <polyline
            points="0,36 20,28 40,32 60,14 80,20 100,10 120,16"
            fill={`${colour}15`}
            stroke="none"
          />
        </svg>
      </Box>
    );
  }

  if (type === "interval_plot") {
    return (
      <Box sx={{ px: 1.5, pb: 1, pt: 0.5, display: "flex", flexDirection: "column", gap: 0.75 }}>
        {[60, 80, 45, 70].map((w, i) => (
          <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: colour, opacity: 0.7 }} />
            <Box sx={{ height: 4, borderRadius: 2, width: `${w}%`, bgcolor: `${colour}40` }} />
          </Box>
        ))}
      </Box>
    );
  }

  if (type === "widget") {
    return (
      <Box
        sx={{
          px: 1.5,
          pb: 1,
          pt: 0.5,
          display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)",
          gridTemplateRows: "repeat(3, 1fr)",
          gap: 0.4,
          height: 52,
        }}
      >
        {Array.from({ length: 15 }).map((_, i) => (
          <Box
            key={i}
            sx={{ borderRadius: 0.5, bgcolor: `${colour}${20 + (i % 5) * 14}` }}
          />
        ))}
      </Box>
    );
  }

  // bar_chart + text
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.5, px: 1.5, pb: 1, pt: 0.5, height: 50 }}>
      {[60, 80, 45, 90, 55, 70].map((h, i) => (
        <Box
          key={i}
          sx={{
            flex: 1,
            borderRadius: "2px 2px 0 0",
            height: `${h}%`,
            bgcolor: i === 3 ? colour : `${colour}50`,
          }}
        />
      ))}
    </Box>
  );
}

interface TypePopoverProps {
  anchorEl: HTMLElement | null;
  currentType: TileType;
  onClose: () => void;
  onChange: (type: TileType) => void;
}

function TypePopover({ anchorEl, currentType, onClose, onChange }: TypePopoverProps) {
  return (
    <Popover
      open={Boolean(anchorEl)}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          sx: { p: 1, borderRadius: 2, boxShadow: 4 },
          onMouseDown: (e: React.MouseEvent) => e.stopPropagation(),
        },
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        display="block"
        sx={{ mb: 0.75, px: 0.5, fontWeight: 600 }}
      >
        Chart type
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.5, width: 200 }}>
        {CHART_TYPES.map((type) => {
          const { Icon, label, colour } = TILE_META[type];
          const isSelected = type === currentType;
          return (
            <Box
              key={type}
              component="button"
              onClick={() => { onChange(type); onClose(); }}
              aria-pressed={isSelected}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.75,
                px: 1,
                py: 0.75,
                border: "1.5px solid",
                borderColor: isSelected ? colour : "divider",
                borderRadius: 1.5,
                bgcolor: isSelected ? `${colour}10` : "transparent",
                cursor: "pointer",
                outline: "none",
                font: "inherit",
                transition: "all 100ms ease-out",
                "&:hover": { borderColor: colour, bgcolor: `${colour}08` },
              }}
            >
              <Icon sx={{ fontSize: 14, color: isSelected ? colour : "text.secondary", flexShrink: 0 }} />
              <Typography
                variant="caption"
                sx={{
                  fontSize: 11,
                  fontWeight: isSelected ? 700 : 400,
                  color: isSelected ? colour : "text.secondary",
                  lineHeight: 1.2,
                }}
              >
                {label}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Popover>
  );
}

export default function TileGrid({
  tiles,
  selectedId,
  onSelect,
  onRemove,
  onTypeChange,
  onLayoutChange,
  onOpenAssistant,
}: TileGridProps) {
  const { width, containerRef, mounted } = useContainerWidth({ measureBeforeMount: true });
  const layout: LayoutItem[] = useMemo(() => tiles.map(tileToLayoutItem), [tiles]);

  const [popover, setPopover] = useState<{
    anchorEl: HTMLElement;
    tileId: string;
    currentType: TileType;
  } | null>(null);

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
    <>
      <Box ref={containerRef} sx={{ width: "100%", minHeight: 400 }}>
        {mounted && (
          <GridLayout
            width={width}
            layout={layout}
            onLayoutChange={handleLayoutChange}
            gridConfig={{ cols: 12, rowHeight: 80 }}
            style={{ minHeight: 400 }}
          >
            {tiles.map((tile) => {
              const meta = TILE_META[tile.tile_type] ?? TILE_META.bar_chart;
              const { Icon, colour, label } = meta;
              const isSelected = tile.tile_id === selectedId;
              const isWidget = tile.tile_type === "widget";
              return (
                <Box
                  key={tile.tile_id}
                  onClick={() => onSelect(tile.tile_id)}
                  sx={{
                    border: "2px solid",
                    borderColor: isSelected ? colour : "divider",
                    borderRadius: 1.5,
                    bgcolor: "background.paper",
                    overflow: "hidden",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    position: "relative",
                    transition: "border-color 120ms ease-out, box-shadow 120ms ease-out",
                    boxShadow: isSelected ? `0 0 0 3px ${colour}25` : "none",
                  }}
                >
                  {/* Colour accent strip */}
                  <span
                    aria-hidden="true"
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: 3,
                      background: colour,
                    }}
                  />

                  {/* Tile header / drag handle */}
                  <Box
                    data-grid-drag-handle
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      px: 1,
                      pl: 1.5,
                      py: 0.5,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      cursor: "grab",
                      gap: 0.5,
                      bgcolor: isSelected ? `${colour}0A` : "grey.50",
                    }}
                  >
                    <DragIndicatorIcon sx={{ fontSize: 12, color: "text.disabled", flexShrink: 0 }} />
                    <Icon sx={{ fontSize: 13, color: colour, flexShrink: 0 }} />
                    <Typography
                      variant="caption"
                      fontWeight={600}
                      flex={1}
                      noWrap
                      sx={{ color: "text.primary", ml: 0.25 }}
                    >
                      {tile.label}
                    </Typography>

                    {/* Chart type button (hidden for widgets) */}
                    {!isWidget && (
                      <Tooltip title="Change chart type">
                        <Box
                          component="button"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation();
                            setPopover({
                              anchorEl: e.currentTarget as HTMLElement,
                              tileId: tile.tile_id,
                              currentType: tile.tile_type,
                            });
                          }}
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 0.25,
                            px: 0.5,
                            py: 0.2,
                            border: "1px solid",
                            borderColor: "divider",
                            borderRadius: 1,
                            bgcolor: "transparent",
                            cursor: "pointer",
                            outline: "none",
                            font: "inherit",
                            flexShrink: 0,
                            transition: "border-color 100ms, bgcolor 100ms",
                            "&:hover": {
                              borderColor: colour,
                              bgcolor: `${colour}0A`,
                            },
                          }}
                          aria-label={`Change chart type, currently ${label}`}
                        >
                          <Typography
                            component="span"
                            variant="caption"
                            sx={{ fontSize: 10, color: "text.secondary", lineHeight: 1 }}
                          >
                            {label}
                          </Typography>
                          <KeyboardArrowDownIcon sx={{ fontSize: 10, color: "text.disabled" }} />
                        </Box>
                      </Tooltip>
                    )}

                    <Tooltip title="Remove tile">
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); onRemove(tile.tile_id); }}
                        onMouseDown={(e) => e.stopPropagation()}
                        aria-label={`Remove ${tile.label}`}
                        sx={{ p: 0.25, color: "text.disabled", "&:hover": { color: "error.main" } }}
                      >
                        <DeleteOutlineIcon sx={{ fontSize: 14 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>

                  {/* Mini preview */}
                  <Box sx={{ flex: 1, overflow: "hidden" }}>
                    <TilePreviewBody type={tile.tile_type} />
                  </Box>

                  {/* Section badge */}
                  {tile.section && (
                    <Box sx={{ px: 1, pb: 0.5, display: "flex", justifyContent: "flex-end" }}>
                      <Typography variant="caption" sx={{ fontSize: 9, color: "text.disabled", fontStyle: "italic" }}>
                        {tile.section}
                      </Typography>
                    </Box>
                  )}
                </Box>
              );
            })}
          </GridLayout>
        )}
      </Box>

      {/* Chart type popover */}
      <TypePopover
        anchorEl={popover?.anchorEl ?? null}
        currentType={popover?.currentType ?? "bar_chart"}
        onClose={() => setPopover(null)}
        onChange={(newType) => {
          if (popover) onTypeChange(popover.tileId, newType);
        }}
      />
    </>
  );
}
