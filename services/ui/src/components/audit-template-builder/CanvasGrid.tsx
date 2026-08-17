"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Canva-style drag-and-drop canvas using @dnd-kit/core.
 *
 * - 12-column CSS grid, 80px row height.
 * - Each tile renders a live MetricTile with mock data (builderMode).
 * - Edit chrome (drag handle, type badge, delete) slides in on hover/select.
 * - DragOverlay renders a semi-transparent ghost while dragging.
 * - Resize handles (SE/S/E) use pointer events directly.
 * - HTML5 drop from the MetricPicker lands at cursor position.
 * - No auto-compaction -- tiles stay exactly where the user places them.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
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
import MetricTile from "@/components/audit-template-renderer/MetricTile";
import ContentBlockTile from "@/components/audit-template-renderer/ContentBlockTile";
import { generateMockData } from "@/lib/auditMockData";
import { isContentBlock } from "@/lib/contentBlocks";
import {
  type AuditTile,
  type MetricCatalogueEntry,
  type TileLayout,
  type TileType,
} from "@/lib/auditTemplateApi";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLS = 12;
const ROW_H = 80; // px per row
const GAP = 12; // px gap between cells

const TILE_META: Record<TileType, { Icon: React.ElementType; colour: string; label: string }> = {
  bar_chart:     { Icon: BarChartIcon,           colour: "#002178", label: "Bar chart" },
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
  catalogue: MetricCatalogueEntry[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onRemove: (id: string) => void;
  onLayoutChange: (tiles: AuditTile[]) => void;
  onTileParamChange?: (tile: AuditTile) => void;
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
    width: 10,
    height: 10,
    background: "#0D99FF",
    border: "2px solid #fff",
    borderRadius: "50%",
    zIndex: 20,
    cursor: dir === "se" ? "se-resize" : dir === "s" ? "s-resize" : "e-resize",
    ...(dir === "se" && { bottom: -5, right: -5 }),
    ...(dir === "s"  && { bottom: -5, left: "50%", transform: "translateX(-50%)" }),
    ...(dir === "e"  && { right: -5,  top: "50%",  transform: "translateY(-50%)" }),
  };

  return (
    <span
      style={pos}
      onPointerDown={handlePointerDown}
      aria-hidden="true"
      data-testid={`resize-handle-${dir}`}
    />
  );
}

// ---------------------------------------------------------------------------
// DraggableTile -- live preview + hover edit chrome
// ---------------------------------------------------------------------------

interface DraggableTileProps {
  tile: AuditTile;
  catalogueEntry?: MetricCatalogueEntry;
  isSelected: boolean;
  isDragging: boolean;
  isGhost?: boolean;
  containerRef: React.RefObject<HTMLDivElement | null>;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
  onResize: (tileId: string, layout: TileLayout) => void;
  onTileParamChange?: (tile: AuditTile) => void;
}

function DraggableTile({
  tile,
  catalogueEntry,
  isSelected,
  isDragging,
  isGhost = false,
  containerRef,
  onSelect,
  onRemove,
  onResize,
  onTileParamChange,
}: DraggableTileProps) {
  const { attributes, listeners, setNodeRef } = useDraggable({ id: tile.tile_id });
  const [hovered, setHovered] = useState(false);
  const meta = TILE_META[tile.tile_type] ?? TILE_META.bar_chart;
  const { Icon, colour, label } = meta;
  const mockData = useMemo(
    () => (catalogueEntry ? generateMockData(catalogueEntry) : undefined),
    [catalogueEntry],
  );
  const showChrome = (hovered || isSelected) && !isGhost;

  const containerStyle: React.CSSProperties = {
    ...(!isGhost ? toGridArea(tile.layout ?? { x: 0, y: 0, w: 4, h: 3 }) : {}),
    position: "relative",
    borderRadius: 10,
    overflow: "hidden",
    cursor: isDragging ? "grabbing" : "grab",
    opacity: isDragging && !isGhost ? 0.4 : 1,
    border: `2px solid ${isSelected ? "#0D99FF" : showChrome ? "#0D99FF50" : "transparent"}`,
    boxShadow: isSelected
      ? "0 0 0 3px #0D99FF26, 0 4px 16px rgba(0,0,0,0.12)"
      : hovered
      ? "0 2px 8px rgba(0,0,0,0.10)"
      : "0 1px 4px rgba(0,0,0,0.07)",
    transition: "box-shadow 120ms, border-color 120ms, opacity 120ms",
    userSelect: "none",
    animation: !isGhost ? "tileEnter 0.18s ease-out" : undefined,
    // Height fills the CSS grid cell (no explicit height needed -- grid defines it)
  };

  return (
    <Box
      ref={!isGhost ? setNodeRef : undefined}
      style={containerStyle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={(e) => { e.stopPropagation(); onSelect(tile.tile_id); }}
      {...(!isGhost ? { ...attributes, ...listeners } : {})}
      data-testid="canvas-tile"
    >
      {/* Live chart preview filling the whole tile */}
      <Box sx={{ position: "absolute", inset: 0 }}>
        {isContentBlock(tile.metric_id)
          ? (
            <ContentBlockTile
              tile={tile}
              builderMode
              isSelected={isSelected}
              onParamChange={onTileParamChange}
            />
          )
          : (
            <MetricTile tile={tile} orgId="" mockData={mockData} builderMode />
          )
        }
      </Box>

      {/* Edit chrome -- slides in over the tile on hover / select */}
      {showChrome && (
        <Box
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0,
            height: 34,
            background: "rgba(255,255,255,0.96)",
            backdropFilter: "blur(6px)",
            borderBottom: "1px solid #E2E8F0",
            display: "flex",
            alignItems: "center",
            paddingLeft: 10,
            paddingRight: 6,
            gap: 4,
            zIndex: 10,
          }}
        >
          <OpenWithIcon sx={{ fontSize: 13, color: "text.disabled", flexShrink: 0 }} />
          <Icon sx={{ fontSize: 12, color: colour, flexShrink: 0, ml: 0.25 }} />
          <Typography variant="caption" fontWeight={700} noWrap sx={{ flex: 1, fontSize: 11 }}>
            {tile.label}
          </Typography>
          <Typography
            component="span"
            variant="caption"
            sx={{ fontSize: 10, color: colour, fontWeight: 600, flexShrink: 0 }}
          >
            {label}
          </Typography>
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
        </Box>
      )}

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
  catalogue,
  selectedId,
  onSelect,
  onRemove,
  onLayoutChange,
  onTileParamChange,
  onOpenAssistant,
  onDropMetric,
  onDropWidget,
}: CanvasGridProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [activeTileId, setActiveTileId] = useState<string | null>(null);
  const [dropGhost, setDropGhost] = useState<{ col: number; row: number } | null>(null);
  const [libDragOver, setLibDragOver] = useState(false);

  const catalogueById = useMemo(
    () => new Map(catalogue.map((m) => [m.metric_id, m])),
    [catalogue],
  );

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
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
          : t,
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
      // Always accept dragover -- Playwright's dragTo doesn't preserve custom
      // dataTransfer types, so we can't type-check here. Validate on drop only.
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
  const canvasRows = isEmpty
    ? 6
    : Math.max(6, ...tiles.map((t) => (t.layout?.y ?? 0) + (t.layout?.h ?? 3))) + 2;

  return (
    <>
      <style>{`@keyframes tileEnter { from { opacity:0; transform:scale(0.96); } to { opacity:1; transform:scale(1); } }`}</style>

      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <Box
          ref={containerRef}
          onClick={() => onSelect(null)}
          onDragOver={handleLibDragOver}
          onDragLeave={handleLibDragLeave}
          onDrop={handleLibDrop}
          data-testid="canvas-grid"
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
              catalogueEntry={catalogueById.get(tile.metric_id)}
              isSelected={tile.tile_id === selectedId}
              isDragging={tile.tile_id === activeTileId}
              containerRef={containerRef}
              onSelect={onSelect}
              onRemove={onRemove}
              onResize={handleResize}
              onTileParamChange={onTileParamChange}
            />
          ))}

          {/* Empty state */}
          {isEmpty && (
            <Box
              style={{ gridColumn: "1 / span 12", gridRow: "2 / span 4", pointerEvents: "none" }}
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 1.5,
                color: "text.disabled",
              }}
            >
              <Typography variant="body2" textAlign="center" sx={{ maxWidth: 340 }}>
                Drag a metric from the library, or click a chart type to add it instantly.
                {onOpenAssistant && " Use AI to describe your report and auto-populate tiles."}
              </Typography>
              {onOpenAssistant && (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AutoAwesomeOutlinedIcon />}
                  onClick={(e) => { e.stopPropagation(); onOpenAssistant(); }}
                  sx={{ pointerEvents: "auto" }}
                >
                  Ask AI
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
                catalogueEntry={catalogueById.get(activeTile.metric_id)}
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
