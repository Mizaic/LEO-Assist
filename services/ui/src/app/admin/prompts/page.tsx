/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCD21209
 *   DI: DI-553F50A2, DI-C5A523A7
 */
"use client";

/**
 * AI Instructions list -- Wave E Phase 4 redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout. This page contributes StatHero, FilterBar,
 * SegmentedTabs, ToolbarActions, and ReviewListCard.
 *
 * Design Controls: DI-LEO-AI-148, DO-LEO-AI-144, VT-LEO-AI-146.
 */

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import AddIcon from "@mui/icons-material/Add";
import {
  FilterBar,
  ReviewListCard,
  SegmentedTabs,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type ReviewListItem,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import {
  CATEGORY_ALL,
  categoriseFromPrompt,
  type PromptConfig,
} from "./promptCategories";
import { GroupHeading, toReviewItem } from "./promptListRows";
import { PromptsEmpty, PromptsNoMatch, SkeletonList } from "./promptListStates";
import { usePromptsList } from "./usePromptsList";

function computeStats(prompts: PromptConfig[]): StatTile[] {
  const total = prompts.length;
  const categories = new Set(prompts.map((p) => categoriseFromPrompt(p).label)).size;
  const withDoubleCheck = prompts.filter((p) => p.verification).length;
  const withExamples = prompts.filter((p) => p.fewShotCount > 0).length;
  return [
    { id: "total", label: "Instruction sets", value: total, tone: "neutral" },
    { id: "categories", label: "Categories covered", value: categories, tone: "neutral" },
    {
      id: "double-check",
      label: "With double-check",
      value: withDoubleCheck,
      tone: withDoubleCheck > 0 ? "positive" : "neutral",
    },
    {
      id: "examples",
      label: "With examples",
      value: withExamples,
      tone: withExamples > 0 ? "positive" : "neutral",
    },
  ];
}

function PromptsToolbar({
  search,
  onSearchChange,
  toolbarActions,
  loading,
  allCategories,
  segmentedTabs,
  activeCategory,
  onCategoryChange,
  filteredCount,
  totalCount,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  toolbarActions: ToolbarAction[];
  loading: boolean;
  allCategories: string[];
  segmentedTabs: Array<{ id: string; label: string; count: number }>;
  activeCategory: string;
  onCategoryChange: (id: string) => void;
  filteredCount: number;
  totalCount: number;
}) {
  return (
    <StickyChrome testId="ai-instructions-chrome">
      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search by name or description"
        aria-label="Search AI instructions"
        trailing={<ToolbarActions actions={toolbarActions} />}
      />
      {!loading && allCategories.length > 1 ? (
        <div style={{ marginTop: 12 }}>
          <SegmentedTabs
            tabs={segmentedTabs}
            value={activeCategory}
            onChange={onCategoryChange}
            aria-label="Filter AI instructions by category"
          />
        </div>
      ) : null}
      {!loading && totalCount > 0 ? (
        <p
          style={{
            margin: "8px 0 0",
            fontSize: 12,
            color: color.text.caption,
            fontFamily: typography.fontFamily.body,
          }}
        >
          {filteredCount} of {totalCount} instruction set{totalCount !== 1 ? "s" : ""}
        </p>
      ) : null}
    </StickyChrome>
  );
}

function PromptsBody({
  loading,
  prompts,
  filtered,
  grouped,
  isFiltering,
  onSelect,
}: {
  loading: boolean;
  prompts: PromptConfig[];
  filtered: PromptConfig[];
  grouped: Array<[string, PromptConfig[]]>;
  isFiltering: boolean;
  onSelect: (id: string) => void;
}) {
  if (loading) return <SkeletonList />;
  if (prompts.length === 0) return <PromptsEmpty />;
  if (filtered.length === 0) return <PromptsNoMatch />;
  return isFiltering ? (
    <ReviewListCard
      items={filtered.map((p) => toReviewItem(p, onSelect)) as ReviewListItem[]}
    />
  ) : (
    <div data-testid="prompts-grouped" style={{ display: "grid", gap: 24 }}>
      {grouped.map(([groupLabel, items]) => (
        <div key={groupLabel}>
          <GroupHeading
            label={groupLabel}
            count={items.length}
            tone={categoriseFromPrompt(items[0]).tone}
          />
          <ReviewListCard
            items={items.map((p) => toReviewItem(p, onSelect)) as ReviewListItem[]}
          />
        </div>
      ))}
    </div>
  );
}

function categoryTabs(prompts: PromptConfig[], allCategories: string[]) {
  return allCategories.map((cat) => ({
    id: cat,
    label: cat,
    count:
      cat === CATEGORY_ALL
        ? prompts.length
        : prompts.filter((p) => categoriseFromPrompt(p).label === cat).length,
  }));
}

export default function PromptsPage() {
  const router = useRouter();
  const list = usePromptsList();
  const stats = useMemo(() => computeStats(list.prompts), [list.prompts]);
  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "new-instructions",
        label: "New instructions",
        onClick: () => router.push("/admin/prompts/new"),
        icon: <AddIcon sx={{ fontSize: 18 }} />,
        variant: "primary",
      },
    ],
    [router],
  );
  const segmentedTabs = useMemo(
    () => categoryTabs(list.prompts, list.allCategories),
    [list.allCategories, list.prompts],
  );

  return (
    <div data-testid="ai-instructions-workspace">
      <StatHero stats={stats} />
      {list.error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => list.setError(null)}>
          {list.error}
        </Alert>
      ) : null}
      <PromptsToolbar
        search={list.search}
        onSearchChange={list.setSearch}
        toolbarActions={toolbarActions}
        loading={list.loading}
        allCategories={list.allCategories}
        segmentedTabs={segmentedTabs}
        activeCategory={list.activeCategory}
        onCategoryChange={list.setActiveCategory}
        filteredCount={list.filtered.length}
        totalCount={list.prompts.length}
      />
      <SpringSwap swapKey={list.activeCategory + ":" + list.search}>
        <PromptsBody
          loading={list.loading}
          prompts={list.prompts}
          filtered={list.filtered}
          grouped={list.grouped}
          isFiltering={list.isFiltering}
          onSelect={(id) => router.push(`/admin/prompts/${id}`)}
        />
      </SpringSwap>
    </div>
  );
}
