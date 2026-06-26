"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Canva-style drag-and-drop canvas using @dnd-kit/core.
 *
 * - 12-column CSS grid, 80px row height.
 * - Tiles are draggable by their full surface (no handle selector).
 * - DragOverlay renders a semi-transparent ghost while dragging.
 * - Resize handles (SE/S/E) use pointer events directly.
 * - HTML5 drop from the MetricPicker lands at cursor position.
 * - No auto-compaction -- tiles stay exactly where the user places them.
 */

import { useCallback, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Button from "@mui/material/Button";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import NumbersIcon from "@mui/icons-material/Numbers";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import TimelineIcon from "@mui/icons-material/Timeline";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import OpenWithIcon from "@mui/icons-material/OpenWith";
import { type AuditTile, type TileLayout, type TileType } from "@/lib/auditTemplateApi";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLS = 12;
const ROW_H = 80; // px per row
const GAP = 12; // px gap between cells

const TILE_META: Record<TileType, { Icon: React.ElementType; colour: string; label: string }> = {
  bar_chart:     { Icon: BarChartIcon,           colour: "#1E40AF", label: "Bar chart" },
  line_chart:    { Icon: ShowChartIcon,           colour: "#047857", label: "Line chart" },
  kpi_strip:     { Icon: NumbersIcon,             colour: "#7C3AED", label: "KPI strip" },
  table:         { Icon: TableChartOutlinedIcon,  colour: "#0E7490", label: "Table" },
  interval_plot: { Icon: TimelineIcon,            colour: "#B45309", label: "Interval plot" },
  text:          { Icon: TextFieldsIcon,          colour: "#475569", label: "Text" },
  widget:        { Icon: WidgetsOutlinedIcon,     colour: "#92400E", label: "Widget" },
};

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface CanvasGridProps {
  tiles: AuditTile[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onRemove: (id: string) => void;
  onLayoutChange: (tiles: AuditTile[]) => void;
  onOpenAssistant?: () => void;
  onDropMetric?: (metricId: string, tileType: TileType, at: { x: number; y: number }) => void;
  onDropWidget?: (widgetId: string, at: { x: number; y: number }) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert pixel offset inside the canvas to a grid cell {col, row}. */
function pixelToCell(
  offsetX: number,
  offsetY: number,
  containerWidth: number,
): { col: number; row: number } {
  const colW = (containerWidth - GAP * (COLS - 1)) / COLS;
  const col = Math.max(0, Math.min(COLS - 1, Math.floor(offsetX / (colW + GAP))));
  const row = Math.max(0, Math.floor(offsetY / (ROW_H + GAP)));
  return { col, row };
}

/** Map tile.layout to CSS grid placement string. */
function toGridArea({ x, y, w, h }: TileLayout): React.CSSProperties {
  return {
    gridColumn: `${x + 1} / span ${w}`,
    gridRow: `${y + 1} / span ${h}`,
  };
}

// ---------------------------------------------------------------------------
// TilePreviewBody (decorative mini chart)
// ---------------------------------------------------------------------------

function TilePreviewBody({ type, colour }: { type: TileType; colour: string }) {
  if (type === "kpi_strip") {
    return (
      <Box sx={{ display: "flex", gap: 1, p: 1.5, pt: 0.5 }}>
        {[48, 38, 56].map((w, i) => (
          <Box
            key={i}
            sx={{
              flex: 1, height: 36, borderRadius: 1,
              bgcolor: `${colour}14`, border: `1px solid ${colour}30`,
              display: "flex", alignItems: "center", justifyContent: "center",
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
            fill="none" stroke={colour} strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" opacity={0.7}
          />
          <polyline
            points="0,36 20,28 40,32 60,14 80,20 100,10 120,16 120,44 0,44"
            fill={`${colour}15`} stroke="none"
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
  // bar_chart, text, widget
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.5, px: 1.5, pb: 1, pt: 0.5, height: 50 }}>
      {[60, 80, 45, 90, 55, 70].map((h, i) => (
        <Box key={i} sx={{ flex: 1, borderRadius: "2px 2px 0 0", height: `${h}%`, bgcolor: i === 3 ? colour : `${colour}50` }} />
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// ResizeHandle
// ---------------------------------------------------------------------------

type ResizeDir = "se" | "s" | "e";

interface ResizeHandleProps {
  dir: ResizeDir;
  tile: AuditTile;
  containerRef: React.RefObject<HTMLDivElement | null>;
  onResize: (tileId: string, layout: TileLayout) => void;
}

function ResizeHandle({ dir, tile, containerRef, onResize }: ResizeHandleProps) {
  const startRef = useRef<{
    pointerX: number; pointerY: number;
    startW: number; startH: number;
    colW: number;
  } | null>(null);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.stopPropagation();
      e.preventDefault();
      const container = containerRef.current;
      if (!container) return;
      const containerW = container.offsetWidth;
      const colW = (containerW - GAP * (COLS - 1)) / COLS;
      startRef.current = {
        pointerX: e.clientX,
        pointerY: e.clientY,
        startW: tile.layout?.w ?? 4,
        startH: tile.layout?.h ?? 3,
        colW,
      };
      const onMove = (ev: PointerEvent) => {
        if (!startRef.current) return;
        const { pointerX, pointerY, startW, startH, colW: cw } = startRef.current;
        const dx = ev.clientX - pointerX;
        const dy = ev.clientY - pointerY;
        const dCols = Math.round(dx / (cw + GAP));
        const dRows = Math.round(dy / (ROW_H + GAP));
        const newW = dir === "s" ? startW : Math.max(1, Math.min(COLS - (tile.layout?.x ?? 0), startW + dCols));
        const newH = dir === "e" ? startH : Math.max(1, startH + dRows);
        onResize(tile.tile_id, {
          x: tile.layout?.x ?? 0,
          y: tile.layout?.y ?? 0,
          w: newW,
          h: newH,
        });
      };
      const onUp = () => {
        startRef.current = null;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [dir, tile, containerRef, onResize],
  );

  const pos: React.CSSProperties = {
    position: "absolute",
    width: 8,
    height: 8,
    background: "#0D99FF",
    borderRadius: 2,
    zIndex: 10,
    cursor: dir === "se" ? "se-resize" : dir === "s" ? "s-resize" : "e-resize",
    ...(dir === "se" && { bottom: -4, right: -4 }),
    ...(dir === "s"  && { bottom: -4, left: "50%", transform: "translateX(-50%)" }),
    ...(dir === "e"  && { right: -4,  top: "50%",  transform: "translateY(-50%)" }),
  };

  return (
    <span
      style={pos}
      onPointerDown={handlePointerDown}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// DraggableTile
// ---------------------------------------------------------------------------

interface DraggableTileProps {
  tile: AuditTile;
  isSelected: boolean;
  isDragging: boolean;
  isGhost?: boolean;
  containerRef: React.RefObject<HTMLDivElement | null>;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
  onResize: (tileId: string, layout: TileLayout) => void;
}

function DraggableTile({
  tile,
  isSelected,
  isDragging,
  isGhost = false,
  containerRef,
  onSelect,
  onRemove,
  onResize,
}: DraggableTileProps) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: tile.tile_id,
  });
  const [hovered, setHovered] = useState(false);
  const meta = TILE_META[tile.tile_type] ?? TILE_META.bar_chart;
  const { Icon, colour, label } = meta;

  const style: React.CSSProperties = {
    ...(!isGhost ? toGridArea(tile.layout ?? { x: 0, y: 0, w: 4, h: 3 }) : {}),
    position: "relative",
    background: "#FFFFFF",
    border: `2px solid ${isSelected ? "#0D99FF" : "transparent"}`,
    borderRadius: 10,
    boxShadow: isSelected
      ? "0 0 0 3px #0D99FF26, 0 4px 12px rgba(0,0,0,0.10)"
      : "0 1px 4px rgba(0,0,0,0.10)",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    cursor: isDragging ? "grabbing" : "grab",
    opacity: isDragging && !isGhost ? 0.4 : 1,
    transition: "box-shadow 120ms, border-color 120ms, opacity 120ms",
    userSelect: "none",
    // entrance fade-in
    animation: !isGhost ? "tileEnter 0.18s ease-out" : undefined,
  };

  return (
    <Box
      ref={!isGhost ? setNodeRef : undefined}
      style={style}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(tile.tile_id);
      }}
      {...(!isGhost ? { ...attributes, ...listeners } : {})}
      data-testid="canvas-tile"
    >
      {/* Colour accent */}
      <span
        aria-hidden="true"
        style={{
          position: "absolute", left: 0, top: 0, bottom: 0, width: 4,
          background: colour, borderRadius: "10px 0 0 10px",
        }}
      />

      {/* Header bar */}
      <Box
        sx={{
          display: "flex", alignItems: "center",
          pl: 1.5, pr: 0.75, py: 0.75,
          borderBottom: "1px solid", borderColor: "divider",
          bgcolor: isSelected ? `${colour}08` : "grey.50",
          minHeight: 36,
          gap: 0.5,
        }}
      >
        <OpenWithIcon sx={{ fontSize: 13, color: "text.disabled", flexShrink: 0, opacity: hovered || isSelected ? 1 : 0.3 }} />
        <Icon sx={{ fontSize: 13, color: colour, flexShrink: 0, ml: 0.25 }} />
        <Typography
          variant="caption" fontWeight={700} flex={1} noWrap
          sx={{ color: "text.primary", ml: 0.25, fontSize: 11 }}
        >
          {tile.label}
        </Typography>
        <Typography
          component="span" variant="caption"
          sx={{ fontSize: 10, color: colour, fontWeight: 600, opacity: 0.7, flexShrink: 0 }}
        >
          {label}
        </Typography>
        {(hovered || isSelected) && !isGhost && (
          <Tooltip title="Remove tile">
            <IconButton
              size="small"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onRemove(tile.tile_id); }}
              aria-label={`Remove ${tile.label}`}
              sx={{ p: 0.25, ml: 0.25, color: "text.disabled", "&:hover": { color: "error.main" } }}
            >
              <DeleteOutlineIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Preview body */}
      <Box sx={{ flex: 1, overflow: "hidden" }} data-testid="tile-body">
        <TilePreviewBody type={tile.tile_type} colour={colour} />
      </Box>

      {/* Resize handles -- visible when selected */}
      {isSelected && !isGhost && (
        <>
          <ResizeHandle dir="se" tile={tile} containerRef={containerRef} onResize={onResize} />
          <ResizeHandle dir="s"  tile={tile} containerRef={containerRef} onResize={onResize} />
          <ResizeHandle dir="e"  tile={tile} containerRef={containerRef} onResize={onResize} />
        </>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// DropGhostCell -- shows where a library metric will land on hover
// ---------------------------------------------------------------------------

interface DropGhostCellProps {
  col: number;
  row: number;
}

function DropGhostCell({ col, row }: DropGhostCellProps) {
  return (
    <Box
      aria-hidden="true"
      style={{
        gridColumn: `${col + 1} / span 4`,
        gridRow: `${row + 1} / span 3`,
        border: "2px dashed #0D99FF",
        borderRadius: 10,
        background: "#0D99FF0A",
        pointerEvents: "none",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Main CanvasGrid
// ---------------------------------------------------------------------------

export default function CanvasGrid({
  tiles,
  selectedId,
  onSelect,
  onRemove,
  onLayoutChange,
  onOpenAssistant,
  onDropMetric,
  onDropWidget,
}: CanvasGridProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [activeTileId, setActiveTileId] = useState<string | null>(null);
  const [dropGhost, setDropGhost] = useState<{ col: number; row: number } | null>(null);
  const [libDragOver, setLibDragOver] = useState(false);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
  );

  // ---- @dnd-kit handlers ---------------------------------------------------

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveTileId(event.active.id as string);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveTileId(null);
      const { active, delta } = event;
      const tileId = active.id as string;
      const tile = tiles.find((t) => t.tile_id === tileId);
      if (!tile || !containerRef.current) return;
      const containerW = containerRef.current.offsetWidth;
      const colW = (containerW - GAP * (COLS - 1)) / COLS;
      const dCols = Math.round(delta.x / (colW + GAP));
      const dRows = Math.round(delta.y / (ROW_H + GAP));
      const oldLayout = tile.layout ?? { x: 0, y: 0, w: 4, h: 3 };
      const newX = Math.max(0, Math.min(COLS - oldLayout.w, oldLayout.x + dCols));
      const newY = Math.max(0, oldLayout.y + dRows);
      if (newX === oldLayout.x && newY === oldLayout.y) return;
      const updated = tiles.map((t) =>
        t.tile_id === tileId
          ? { ...t, layout: { ...oldLayout, x: newX, y: newY } }
          : t
      );
      onLayoutChange(updated);
    },
    [tiles, onLayoutChange],
  );

  // ---- Resize handler ------------------------------------------------------

  const handleResize = useCallback(
    (tileId: string, layout: TileLayout) => {
      onLayoutChange(tiles.map((t) => (t.tile_id === tileId ? { ...t, layout } : t)));
    },
    [tiles, onLayoutChange],
  );

  // ---- HTML5 library drop handlers -----------------------------------------

  const getDropCell = useCallback(
    (e: React.DragEvent): { col: number; row: number } | null => {
      if (!containerRef.current) return null;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top + containerRef.current.scrollTop;
      return pixelToCell(x, y, containerRef.current.offsetWidth);
    },
    [],
  );

  const handleLibDragOver = useCallback(
    (e: React.DragEvent) => {
      const types = Array.from(e.dataTransfer.types);
      if (!types.includes("application/x-audit-metric") && !types.includes("application/x-audit-widget")) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      setLibDragOver(true);
      const cell = getDropCell(e);
      if (cell) setDropGhost(cell);
    },
    [getDropCell],
  );

  const handleLibDragLeave = useCallback((e: React.DragEvent) => {
    if (!containerRef.current?.contains(e.relatedTarget as Node)) {
      setLibDragOver(false);
      setDropGhost(null);
    }
  }, []);

  const handleLibDrop = useCallback(
    (e: React.DragEvent) => {
      setLibDragOver(false);
      setDropGhost(null);
      const cell = getDropCell(e) ?? { col: 0, row: 0 };
      const metricRaw = e.dataTransfer.getData("application/x-audit-metric");
      if (metricRaw && onDropMetric) {
        e.preventDefault();
        try {
          const { metric_id, tile_type } = JSON.parse(metricRaw);
          onDropMetric(metric_id, tile_type as TileType, { x: cell.col, y: cell.row });
        } catch { /* ignore */ }
        return;
      }
      const widgetRaw = e.dataTransfer.getData("application/x-audit-widget");
      if (widgetRaw && onDropWidget) {
        e.preventDefault();
        try {
          const { widget_id } = JSON.parse(widgetRaw);
          onDropWidget(widget_id, { x: cell.col, y: cell.row });
        } catch { /* ignore */ }
      }
    },
    [getDropCell, onDropMetric, onDropWidget],
  );

  // ---- Render --------------------------------------------------------------

  const activeTile = tiles.find((t) => t.tile_id === activeTileId) ?? null;
  const isEmpty = tiles.length === 0;
  const canvasRows = isEmpty ? 6 : Math.max(6, ...tiles.map((t) => (t.layout?.y ?? 0) + (t.layout?.h ?? 3))) + 2;

  return (
    <>
      {/* CSS keyframes for tile entrance */}
      <style>{`@keyframes tileEnter { from { opacity:0; transform:scale(0.96); } to { opacity:1; transform:scale(1); } }`}</style>

      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <Box
          ref={containerRef}
          onClick={() => onSelect(null)}
          onDragOver={handleLibDragOver}
          onDragLeave={handleLibDragLeave}
          onDrop={handleLibDrop}
          sx={{
            position: "relative",
            width: "100%",
            minHeight: 520,
            display: "grid",
            gridTemplateColumns: `repeat(${COLS}, 1fr)`,
            gridTemplateRows: `repeat(${canvasRows}, ${ROW_H}px)`,
            gap: `${GAP}px`,
            p: 2,
            borderRadius: 2,
            bgcolor: "#F8FAFC",
            backgroundImage: libDragOver
              ? "none"
              : "radial-gradient(circle, #CBD5E1 1px, transparent 1px)",
            backgroundSize: "24px 24px",
            backgroundPosition: "12px 12px",
            outline: libDragOver ? "2px dashed #0D99FF" : "none",
            outlineOffset: -2,
            transition: "outline-color 120ms, background-color 120ms",
          }}
        >
          {/* Drop ghost preview */}
          {dropGhost && <DropGhostCell col={dropGhost.col} row={dropGhost.row} />}

          {/* Render tiles */}
          {tiles.map((tile) => (
            <DraggableTile
              key={tile.tile_id}
              tile={tile}
              isSelected={tile.tile_id === selectedId}
              isDragging={tile.tile_id === activeTileId}
              containerRef={containerRef}
              onSelect={onSelect}
              onRemove={onRemove}
              onResize={handleResize}
            />
          ))}

          {/* Empty state */}
          {isEmpty && (
            <Box
              style={{
                gridColumn: "1 / span 12",
                gridRow: "2 / span 4",
                pointerEvents: "none",
              }}
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 1.5,
                color: "text.disabled",
              }}
            >
              <Typography variant="body2" textAlign="center" sx={{ maxWidth: 320 }}>
                Drag a metric from the library on the left, or click a chart type to add it.
                {onOpenAssistant && " You can also use AI to describe your dashboard."}
              </Typography>
              {onOpenAssistant && (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AutoAwesomeOutlinedIcon />}
                  onClick={(e) => { e.stopPropagation(); onOpenAssistant(); }}
                  sx={{ pointerEvents: "auto" }}
                >
                  AI
                </Button>
              )}
            </Box>
          )}
        </Box>

        {/* Drag overlay (ghost copy while dragging) */}
        <DragOverlay dropAnimation={null}>
          {activeTile && (
            <Box
              sx={{
                width: `${((activeTile.layout?.w ?? 4) / COLS) * 100}%`,
                height: (activeTile.layout?.h ?? 3) * (ROW_H + GAP) - GAP,
                opacity: 0.85,
                borderRadius: 2,
                overflow: "hidden",
                pointerEvents: "none",
              }}
            >
              <DraggableTile
                tile={activeTile}
                isSelected={false}
                isDragging={false}
                isGhost
                containerRef={containerRef}
                onSelect={() => {}}
                onRemove={() => {}}
                onResize={() => {}}
              />
            </Box>
          )}
        </DragOverlay>
      </DndContext>
    </>
  );
}
