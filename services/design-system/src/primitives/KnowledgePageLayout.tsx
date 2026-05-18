/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
"use client";

import type { ReactNode } from "react";

import { IntroCard, type IntroRoleCopy } from "./IntroCard";
import { StatHero, type StatTile } from "./StatHero";
import type { Role } from "../roles/types";

// Width variants per DI-LEO-AI-144.
// - reading (1280): default, comfortable column for intro-heavy pages
//   (Clinical Guidelines, AI Instructions).
// - wide (1600): data-heavy tabs that benefit from extra horizontal room
//   (Training Data, Surface Forms, Domains, Terminology, Context Rules).
// - fluid: edge-to-edge with viewport gutters only, for power-user queues.
export type KnowledgeLayoutWidth = "reading" | "wide" | "fluid";

const WIDTH_PX: Record<Exclude<KnowledgeLayoutWidth, "fluid">, number> = {
  reading: 1280,
  wide: 1600,
};

export interface KnowledgePageLayoutProps {
  // Stable identifier used by IntroCard for localStorage persistence and
  // test targeting. Every tab should pass a unique screenId.
  screenId: string;
  intro?: IntroRoleCopy;
  role?: Role | null;
  stats?: StatTile[];
  children?: ReactNode;
  // Column width. Defaults to "reading" to preserve existing behaviour.
  width?: KnowledgeLayoutWidth;
}

export function KnowledgePageLayout({
  screenId,
  intro,
  role,
  stats,
  children,
  width = "reading",
}: KnowledgePageLayoutProps) {
  const maxWidth = width === "fluid" ? "100%" : `${WIDTH_PX[width]}px`;
  return (
    <div
      data-testid={"knowledge-layout-" + screenId}
      data-width={width}
      style={{
        maxWidth,
        margin: "0 auto",
        padding: "24px 24px 32px 24px",
        boxSizing: "border-box",
      }}
    >
      {intro ? (
        <IntroCard screenId={screenId} copy={intro} role={role ?? null} />
      ) : null}
      {stats && stats.length > 0 ? <StatHero stats={stats} /> : null}
      <div>{children}</div>
    </div>
  );
}
