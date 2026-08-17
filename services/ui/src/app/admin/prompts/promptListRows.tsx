/**
 * Atlas trace:
 *   DO: DO-BCD21209
 *   DI: DI-553F50A2, DI-C5A523A7
 */
"use client";

import type { ReactNode } from "react";
import type { ReviewListItem } from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";
import SearchIcon from "@mui/icons-material/Search";
import CategoryIcon from "@mui/icons-material/Category";
import BuildIcon from "@mui/icons-material/Build";
import VerifiedIcon from "@mui/icons-material/Verified";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import MergeTypeIcon from "@mui/icons-material/MergeType";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

import {
  categoriseFromPrompt,
  humanName,
  type CategoryTone,
  type PromptConfig,
} from "./promptCategories";

function formatDate(iso: string): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return d.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return null;
  }
}

function categoryIcon(label: string): ReactNode {
  if (label === "Extraction") return <SearchIcon sx={{ fontSize: 16 }} />;
  if (label === "Classification") return <FilterAltIcon sx={{ fontSize: 16 }} />;
  if (label === "Disambiguation") return <ManageSearchIcon sx={{ fontSize: 16 }} />;
  if (label === "Verification") return <VerifiedIcon sx={{ fontSize: 16 }} />;
  if (label === "Episode builder") return <MergeTypeIcon sx={{ fontSize: 16 }} />;
  if (label === "Labelling") return <CategoryIcon sx={{ fontSize: 16 }} />;
  return <BuildIcon sx={{ fontSize: 16 }} />;
}

function ToneMark({ tone, label }: { tone: CategoryTone; label: string }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 28,
        height: 28,
        borderRadius: 999,
        background: tone.bg,
        color: tone.color,
        flexShrink: 0,
      }}
    >
      {categoryIcon(label)}
    </span>
  );
}

function TokenChip({ label, tone }: { label: string; tone?: CategoryTone }) {
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        borderRadius: 999,
        padding: "2px 8px",
        color: tone?.color ?? color.text.secondary,
        background: tone?.bg ?? color.surface.alt,
      }}
    >
      {label}
    </span>
  );
}

export function promptTitle(p: PromptConfig): ReactNode {
  const cat = categoriseFromPrompt(p);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <ToneMark tone={cat.tone} label={cat.label} />
      <span style={{ fontWeight: 600, fontFamily: typography.fontFamily.body }}>
        {humanName(p.name)}
      </span>
    </span>
  );
}

export function promptMeta(p: PromptConfig): ReactNode {
  const date = formatDate(p.updatedAt);
  const description =
    p.description?.trim() || "No description yet -- click to add one.";
  return (
    <>
      <span
        style={{
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          maxWidth: 640,
          fontStyle: p.description?.trim() ? "normal" : "italic",
        }}
      >
        {description}
      </span>
      {date ? <span>Updated {date}</span> : null}
    </>
  );
}

export function promptChips(p: PromptConfig): ReactNode {
  const cat = categoriseFromPrompt(p);
  return (
    <>
      <TokenChip label={cat.label} tone={cat.tone} />
      <TokenChip label={"v" + p.version} />
      {p.verification ? (
        <span title="A second AI check runs after the first to confirm accuracy">
          <TokenChip label="Double-check" tone={{ color: color.status.success, bg: "rgba(4, 120, 87, 0.12)" }} />
        </span>
      ) : null}
      {p.fewShotCount > 0 ? (
        <TokenChip
          label={p.fewShotCount + " example" + (p.fewShotCount !== 1 ? "s" : "")}
        />
      ) : null}
    </>
  );
}

export function toReviewItem(
  p: PromptConfig,
  onSelect: (id: string) => void,
): ReviewListItem {
  return {
    id: p.id,
    title: promptTitle(p),
    meta: promptMeta(p),
    chips: promptChips(p),
    actions: (
      <ChevronRightIcon aria-hidden="true" sx={{ color: color.text.caption, fontSize: 22 }} />
    ),
    onSelect: () => onSelect(p.id),
    tone: "neutral",
  };
}

export function GroupHeading({
  label,
  count,
  tone,
}: {
  label: string;
  count: number;
  tone: CategoryTone;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 8,
      }}
    >
      <ToneMark tone={tone} label={label} />
      <strong
        style={{
          fontFamily: typography.fontFamily.heading,
          fontSize: 16,
          letterSpacing: typography.letterSpacing.display,
          color: color.text.primary,
        }}
      >
        {label}
      </strong>
      <span style={{ fontSize: 12, color: color.text.caption }}>
        {count} instruction{count !== 1 ? "s" : ""}
      </span>
    </div>
  );
}
