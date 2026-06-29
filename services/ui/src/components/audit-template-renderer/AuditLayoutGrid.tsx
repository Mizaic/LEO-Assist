"use client";

/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-758B73A5
 *
 * Renders report tiles at the exact grid positions authored in the builder
 * (tile.layout x/y/w/h on a 12-column grid). Collapses to a single column on
 * small screens so the report stays readable on phones and tablets.
 */

import Box from "@mui/material/Box";

import type { AuditTile, MetricCatalogueEntry, MetricRunResult } from "@/lib/auditTemplateApi";
import { isContentBlock } from "@/lib/contentBlocks";
import MetricTile from "./MetricTile";
import WidgetTile from "./WidgetTile";
import ContentBlockTile from "./ContentBlockTile";

const COLS = 12;
const ROW_HEIGHT = 80;
const GAP = 12;

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

/** True when the tile set was positioned by the user in the builder.
 *
 * The old heuristic (any tile with x>0 or y>0) wrongly returns false for
 * templates where all tiles sit in column 0 with custom sizes. The new
 * heuristic: always treat a non-empty tile set as authored so the renderer
 * always uses the grid positions the builder stored. The section-band fallback
 * in AuditTemplateRenderer is only used when there are NO tiles at all.
 */
export function hasAuthoredLayout(tiles: AuditTile[]): boolean {
  return tiles.length > 0;
}

interface AuditLayoutGridProps {
  tiles: AuditTile[];
  orgId: string;
  mockDataMap: Map<string, MetricRunResult>;
  catalogue?: MetricCatalogueEntry[];
}

export default function AuditLayoutGrid({
  tiles,
  orgId,
  mockDataMap,
}: AuditLayoutGridProps) {
  // Stable top-to-bottom, left-to-right order drives the single-column collapse.
  const ordered = [...tiles].sort(
    (a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x,
  );

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: `repeat(${COLS}, 1fr)` },
        gridAutoRows: { xs: "auto", md: `${ROW_HEIGHT}px` },
        columnGap: `${GAP}px`,
        rowGap: `${GAP}px`,
      }}
    >
      {ordered.map((tile) => {
        const w = clamp(tile.layout.w || 4, 1, COLS);
        const x = clamp(tile.layout.x || 0, 0, COLS - 1);
        const h = Math.max(1, tile.layout.h || 3);
        const y = Math.max(0, tile.layout.y || 0);
        return (
          <Box
            key={tile.tile_id}
            sx={{
              minWidth: 0,
              gridColumn: { xs: "1 / -1", md: `${x + 1} / span ${w}` },
              gridRow: { xs: "auto", md: `${y + 1} / span ${h}` },
            }}
          >
            {isContentBlock(tile.metric_id) ? (
              <ContentBlockTile tile={tile} />
            ) : tile.tile_type === "widget" ? (
              <WidgetTile tile={tile} orgId={orgId} />
            ) : (
              <MetricTile tile={tile} orgId={orgId} mockData={mockDataMap.get(tile.metric_id)} />
            )}
          </Box>
        );
      })}
    </Box>
  );
}
