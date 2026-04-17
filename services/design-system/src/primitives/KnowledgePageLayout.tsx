"use client";

import type { ReactNode } from "react";

import { IntroCard, type IntroRoleCopy } from "./IntroCard";
import { StatHero, type StatTile } from "./StatHero";
import type { Role } from "../roles/types";

export interface KnowledgePageLayoutProps {
  // Stable identifier used by IntroCard for localStorage persistence and
  // test targeting. Every tab should pass a unique screenId.
  screenId: string;
  intro?: IntroRoleCopy;
  role?: Role | null;
  stats?: StatTile[];
  children?: ReactNode;
}

export function KnowledgePageLayout({
  screenId,
  intro,
  role,
  stats,
  children,
}: KnowledgePageLayoutProps) {
  return (
    <div
      data-testid={"knowledge-layout-" + screenId}
      style={{
        maxWidth: 1280,
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
