/**
 * Validation Lab home cards and findings strip.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import type { CSSProperties, ReactNode } from "react";
import { motion as fm } from "framer-motion";
import CreateOutlinedIcon from "@mui/icons-material/CreateOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import PlaylistPlayOutlinedIcon from "@mui/icons-material/PlaylistPlayOutlined";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import type { HomeDoor } from "./accuracyLoopDoors";
import { categoryLabel, type ValidationFinding } from "./findingTypes";

export function DoorCard({
  door,
  index,
  goldCount,
  onClick,
}: {
  door: HomeDoor;
  index: number;
  goldCount?: number;
  onClick: () => void;
}) {
  const { reducedMotion } = useMotion();
  const accent = doorAccent(door.tone);
  const enter = springOrInstant(reducedMotion, springs.ui);
  return (
    <fm.button
      type="button"
      data-testid={door.testId}
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...enter, delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04 }}
      whileTap={tapScale(reducedMotion)}
      onClick={onClick}
      style={cardStyle()}
    >
      <span aria-hidden="true" style={accentStyle(accent)} />
      <DoorCardHeader door={door} accent={accent} goldCount={goldCount} />
      {door.steps.map((step) => (
        <p key={step} style={stepStyle()}>
          {step}
        </p>
      ))}
    </fm.button>
  );
}

function DoorCardHeader({
  door,
  accent,
  goldCount,
}: {
  door: HomeDoor;
  accent: string;
  goldCount?: number;
}) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <span style={iconWell(accent)}>{doorIcon(door.id, accent)}</span>
      <div>
        <p style={headlineStyle()}>{door.headline}</p>
        <p style={bodyStyle()}>{door.description}</p>
        {goldCount === undefined ? null : (
          <p style={bodyStyle()}>
            {goldCount === 0
              ? "None yet. Save gold after a run looks right."
              : `${goldCount} gold cases ready.`}
          </p>
        )}
      </div>
    </div>
  );
}

export function FindingsStrip({
  openFindings,
  onOpenFinding,
}: {
  openFindings: ValidationFinding[];
  onOpenFinding: (runId: string) => void;
}) {
  return (
    <div data-testid="validation-lab-home-strip" style={stripStyle()}>
      <p style={headlineStyle()}>Open findings</p>
      {openFindings.length === 0 ? (
        <p style={bodyStyle()}>No open findings.</p>
      ) : (
        openFindings.slice(0, 8).map((row) => (
          <button
            key={row.id}
            type="button"
            onClick={() => onOpenFinding(row.run_id)}
            style={linkStyle()}
          >
            {categoryLabel(row.category)} -- {row.target || row.note || row.run_id}
          </button>
        ))
      )}
    </div>
  );
}

function doorAccent(tone: HomeDoor["tone"]): string {
  if (tone === "danger") return color.status.danger;
  if (tone === "success") return color.status.success;
  return color.brand.primary;
}

function doorIcon(id: HomeDoor["id"], accent: string): ReactNode {
  const sx = { fontSize: 22, color: accent };
  if (id === "clinical") return <FolderOpenOutlinedIcon sx={sx} />;
  if (id === "saved") return <PlaylistPlayOutlinedIcon sx={sx} />;
  return <CreateOutlinedIcon sx={sx} />;
}

function cardStyle(): CSSProperties {
  return {
    background: color.surface.raised,
    border: 0,
    borderRadius: 12,
    padding: 18,
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: 8,
    position: "relative",
    minHeight: 168,
    width: "100%",
    textAlign: "left",
    boxShadow: elevation.card,
    fontFamily: typography.fontFamily.body,
  };
}

function accentStyle(accent: string): CSSProperties {
  return {
    position: "absolute",
    left: 0,
    top: 14,
    bottom: 14,
    width: 3,
    borderRadius: 2,
    background: accent,
  };
}

function iconWell(accent: string): CSSProperties {
  return {
    width: 40,
    height: 40,
    borderRadius: 12,
    background: color.surface.alt,
    color: accent,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  };
}

function headlineStyle(): CSSProperties {
  return {
    margin: 0,
    fontFamily: typography.fontFamily.heading,
    fontWeight: 700,
    fontSize: 16,
    color: color.text.primary,
  };
}

function bodyStyle(): CSSProperties {
  return {
    margin: "4px 0 0",
    fontSize: 13,
    lineHeight: 1.45,
    color: color.text.secondary,
  };
}

function stepStyle(): CSSProperties {
  return {
    margin: 0,
    fontSize: 13,
    color: color.text.secondary,
  };
}

function stripStyle(): CSSProperties {
  return {
    background: color.surface.raised,
    borderRadius: 12,
    padding: 18,
    boxShadow: elevation.card,
  };
}

function linkStyle(): CSSProperties {
  return {
    display: "block",
    width: "100%",
    textAlign: "left",
    border: 0,
    background: "none",
    padding: "4px 0",
    cursor: "pointer",
    fontSize: 13,
    color: color.brand.primary,
    fontFamily: typography.fontFamily.body,
  };
}
