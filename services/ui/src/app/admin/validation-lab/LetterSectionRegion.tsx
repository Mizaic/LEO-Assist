/**
 * Optional section-region wrap for Teach this form letter focus.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */
"use client";

import {
  createContext,
  useContext,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import Box from "@mui/material/Box";

import {
  regionHitForText,
  type LetterSectionRegion,
} from "@/components/operations/formSchemaSectionFocus";

export interface LetterRegionFocus {
  regions: LetterSectionRegion[];
  highlightedRegionId?: string | null;
  onSelectRegion?: (regionId: string, clickedText: string) => void;
  firstByRegion: Record<string, string>;
}

export const LetterRegionFocusContext =
  createContext<LetterRegionFocus | null>(null);

export function LetterRegionWrap({
  text,
  children,
  as = "div",
}: {
  text: string;
  children: ReactNode;
  as?: "div" | "span";
}): ReactNode {
  const focus = useContext(LetterRegionFocusContext);
  if (!focus?.regions.length) return children;
  const hit = regionHitForText(focus.regions, text);
  if (!hit) return children;
  const highlighted = focus.highlightedRegionId === hit.regionId;
  if (highlighted && !focus.firstByRegion[hit.regionId]) {
    focus.firstByRegion[hit.regionId] = text;
  }
  const showHighlight =
    highlighted && focus.firstByRegion[hit.regionId] === text;
  return (
    <Box
      component={as}
      role="button"
      tabIndex={0}
      data-section-region={hit.regionId}
      data-section-highlight={showHighlight ? "true" : undefined}
      aria-current={showHighlight ? "true" : undefined}
      onClick={(event: MouseEvent<HTMLElement>) => {
        event.stopPropagation();
        focus.onSelectRegion?.(hit.regionId, text);
      }}
      onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        focus.onSelectRegion?.(hit.regionId, text);
      }}
      sx={{
        display: "block",
        cursor: "pointer",
        borderRadius: "4px",
        border: "2px solid",
        borderColor: showHighlight ? "primary.main" : "transparent",
        outline: showHighlight ? "2px solid" : "none",
        outlineColor: showHighlight ? "primary.main" : undefined,
        outlineOffset: showHighlight ? "2px" : undefined,
        bgcolor: showHighlight ? "action.selected" : undefined,
        px: showHighlight ? 0.5 : 0,
      }}
    >
      {children}
    </Box>
  );
}
