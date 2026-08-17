/**
 * Atlas trace:
 *   DO: DO-BCD21209
 *   DI: DI-553F50A2, DI-C5A523A7
 */
"use client";

import { EmptyState } from "@leo/design-system";
import { color, elevation, radius } from "@leo/design-system/tokens";
import SearchIcon from "@mui/icons-material/Search";
import TuneIcon from "@mui/icons-material/Tune";

export function SkeletonList() {
  return (
    <div data-testid="prompts-skeleton-list" style={{ display: "grid", gap: 8 }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 88,
            borderRadius: radius.md,
            boxShadow: elevation.card,
            background: color.surface.raised,
          }}
        />
      ))}
    </div>
  );
}

export function PromptsEmpty() {
  return (
    <EmptyState
      data-testid="prompts-empty"
      icon={<TuneIcon />}
      title="No instructions yet"
      body="Add your first set of AI instructions to get the pipeline working."
    />
  );
}

export function PromptsNoMatch() {
  return (
    <EmptyState
      data-testid="prompts-no-match"
      icon={<SearchIcon />}
      title="No matches"
      body="Try a different search term or pick a different category."
    />
  );
}
