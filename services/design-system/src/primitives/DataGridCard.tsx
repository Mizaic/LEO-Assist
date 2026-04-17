"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";

export interface DataGridColumn<T> {
  id: string;
  header: ReactNode;
  width?: string;
  align?: "left" | "right";
  // Renders the cell content for a row. Keep render pure -- no fetches.
  render: (item: T) => ReactNode;
}

export interface DataGridCardProps<T> {
  columns: DataGridColumn<T>[];
  rows: T[];
  rowKey: (item: T) => string;
  emptyState?: ReactNode;
  onRowClick?: (item: T) => void;
  dense?: boolean;
}

/**
 * DataGridCard -- standard list shell used by the four CRUD tabs
 * (Surface Forms, Context Rules, Domains, Terminology). Rows animate
 * in with a short fade + translate; animations are disabled for
 * reduced-motion. The shell is a semantic <table> so assistive tech
 * can navigate it.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function headerCellStyle(dense: boolean, align: "left" | "right"): React.CSSProperties {
  return {
    textAlign: align,
    fontSize: 12,
    fontWeight: 600,
    color: color.text.caption,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    padding: dense ? "8px 12px" : "10px 14px",
    borderBottom: "1px solid " + color.surface.divider,
    background: color.surface.alt,
    position: "sticky",
    top: 0,
    zIndex: 1,
  };
}

function cellStyle(dense: boolean, align: "left" | "right"): React.CSSProperties {
  return {
    textAlign: align,
    fontSize: 14,
    color: color.text.primary,
    padding: dense ? "10px 12px" : "14px 14px",
    borderBottom: "1px solid " + color.surface.divider,
    fontFamily: typography.fontFamily.body,
  };
}

export function DataGridCard<T>({
  columns,
  rows,
  rowKey,
  emptyState,
  onRowClick,
  dense = false,
}: DataGridCardProps<T>) {
  const { reducedMotion } = useMotion();

  if (rows.length === 0 && emptyState) {
    return (
      <div
        data-testid="data-grid-empty"
        style={{
          padding: 40,
          textAlign: "center",
          fontFamily: typography.fontFamily.body,
          color: color.text.caption,
          border: "1px dashed " + color.surface.divider,
          borderRadius: radius.md,
          background: color.surface.raised,
        }}
      >
        {emptyState}
      </div>
    );
  }

  return (
    <div
      data-testid="data-grid-card"
      style={{
        background: color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderRadius: radius.md,
        overflow: "hidden",
      }}
    >
      <table
        role="grid"
        style={{
          width: "100%",
          borderCollapse: "separate",
          borderSpacing: 0,
          fontFamily: typography.fontFamily.body,
        }}
      >
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.id}
                scope="col"
                style={{
                  width: c.width ?? "auto",
                  ...headerCellStyle(dense, c.align ?? "left"),
                }}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <AnimatePresence initial={!reducedMotion}>
            {rows.map((row, idx) => (
              <fm.tr
                key={rowKey(row)}
                layout
                initial={reducedMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reducedMotion ? undefined : { opacity: 0, y: -4 }}
                transition={{
                  duration: reducedMotion ? 0 : 0.16,
                  ease: "easeOut",
                  delay: reducedMotion ? 0 : Math.min(idx, 20) * 0.02,
                }}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                data-testid={"data-grid-row-" + rowKey(row)}
                style={{
                  cursor: onRowClick ? "pointer" : "default",
                  background: idx % 2 === 0 ? color.surface.raised : color.surface.alt,
                }}
              >
                {columns.map((c) => (
                  <td
                    key={c.id}
                    style={cellStyle(dense, c.align ?? "left")}
                  >
                    {c.render(row)}
                  </td>
                ))}
              </fm.tr>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
    </div>
  );
}
