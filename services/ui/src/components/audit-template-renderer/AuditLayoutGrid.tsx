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

import { motion as fm, useReducedMotion } from "framer-motion";
import Box from "@mui/material/Box";

import type { AuditTile, MetricCatalogueEntry, MetricRunResult } from "@/lib/auditTemplateApi";
import MetricTile from "./MetricTile";
import WidgetTile from "./WidgetTile";

const COLS = 12;
const ROW_HEIGHT = 80;
const GAP = 12;

const MotionBox = fm(Box);

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" } },
};

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

/** True when at least one tile has been positioned away from the origin. */
export function hasAuthoredLayout(tiles: AuditTile[]): boolean {
  return tiles.some((t) => (t.layout?.x ?? 0) > 0 || (t.layout?.y ?? 0) > 0);
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
  const reduced = useReducedMotion();
  // Stable top-to-bottom, left-to-right order drives the single-column collapse.
  const ordered = [...tiles].sort(
    (a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x,
  );

  return (
    <MotionBox
      variants={reduced ? {} : { hidden: {}, visible: { transition: { staggerChildren: 0.05 } } }}
      initial="hidden"
      animate="visible"
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
          <MotionBox
            key={tile.tile_id}
            variants={reduced ? {} : itemVariants}
            sx={{
              minWidth: 0,
              // Honour the authored position on md+; stack full-width below md.
              gridColumn: { xs: "1 / -1", md: `${x + 1} / span ${w}` },
              gridRow: { xs: "auto", md: `${y + 1} / span ${h}` },
            }}
          >
            {tile.tile_type === "widget" ? (
              <WidgetTile tile={tile} orgId={orgId} />
            ) : (
              <MetricTile tile={tile} orgId={orgId} mockData={mockDataMap.get(tile.metric_id)} />
            )}
          </MotionBox>
        );
      })}
    </MotionBox>
  );
}
