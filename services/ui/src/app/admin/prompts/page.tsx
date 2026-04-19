"use client";

/**
 * AI Instructions list -- Wave E Phase 4 redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: total instructions / categories covered / with
 *     double-check / with examples at a glance.
 *   - FilterBar: free-text search with the New-instructions
 *     ToolbarAction in the trailing slot.
 *   - SegmentedTabs: category filter (All / Extraction / etc.).
 *   - ReviewListCard: one row per instruction set, grouped by
 *     category in browse mode; one flat ReviewListCard when filtering.
 *
 * Detail-page rebuild (PromptEditorCard + few-shot library on
 * ReviewListCard) is deferred to a dedicated session given the
 * detail page is a 1.1k LOC editor.
 *
 * Design Controls: DI-LEO-AI-148, DO-LEO-AI-144, VT-LEO-AI-146.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { sortByIsoDateDesc } from "@/lib/dateSort";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import AddIcon from "@mui/icons-material/Add";
import TuneIcon from "@mui/icons-material/Tune";
import SearchIcon from "@mui/icons-material/Search";
import CategoryIcon from "@mui/icons-material/Category";
import BuildIcon from "@mui/icons-material/Build";
import VerifiedIcon from "@mui/icons-material/Verified";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import MergeTypeIcon from "@mui/icons-material/MergeType";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import {
  FilterBar,
  ReviewListCard,
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type ReviewListItem,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";
import { api } from "@/lib/api";

interface PromptConfig {
  id: string;
  name: string;
  description: string;
  version: number;
  verification: boolean;
  fewShotCount: number;
  updatedAt: string;
}

type PromptCategory = {
  color: string;
  bg: string;
  icon: React.ReactNode;
  label: string;
};

// -- Helpers -----------------------------------------------------------------

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

// Visual styling per SBAR context group, keyed by the [<Group>] prefix
// the seed script writes into the PromptConfig description (DI-LEO-AI-507).
const SBAR_CONTEXT_GROUP_STYLE: Record<
  string,
  { color: string; bg: string }
> = {
  "Primary care": { color: "#1565c0", bg: "#e3f2fd" },
  "Secondary care": { color: "#ad1457", bg: "#fce4ec" },
  "Statutory and social": { color: "#4527a0", bg: "#ede7f6" },
  "Quality assurance": { color: "#2e7d32", bg: "#e8f5e9" },
};

const SBAR_CONTEXT_GROUP_FALLBACK = {
  color: "#37474f",
  bg: "#eceff1",
};

function categorise(name: string, description?: string): PromptCategory {
  // SBAR per-context Situation snippets group by the `[<Group>]`
  // prefix in their seeded description so the AI Instructions list
  // shows them under the clinical setting (Primary / Secondary /
  // Statutory / Quality assurance) rather than dumped under General.
  if (name.startsWith("sbar_situation_context_")) {
    const match = description?.match(/^\[([^\]]+)\]/);
    const group = match?.[1]?.trim() ?? "Summarisation context";
    const style = SBAR_CONTEXT_GROUP_STYLE[group] ?? SBAR_CONTEXT_GROUP_FALLBACK;
    return {
      color: style.color,
      bg: style.bg,
      icon: <CategoryIcon sx={{ fontSize: 18 }} />,
      label: group,
    };
  }
  const n = name.toLowerCase();
  if (n.includes("extract")) {
    return {
      color: "#1565c0",
      bg: "#e3f2fd",
      icon: <SearchIcon sx={{ fontSize: 18 }} />,
      label: "Extraction",
    };
  }
  if (
    n.includes("classif") ||
    n.includes("detect") ||
    n.includes("exclusion")
  ) {
    return {
      color: "#6a1b9a",
      bg: "#f3e5f5",
      icon: <FilterAltIcon sx={{ fontSize: 18 }} />,
      label: "Classification",
    };
  }
  if (n.includes("disambig")) {
    return {
      color: "#e65100",
      bg: "#fff3e0",
      icon: <ManageSearchIcon sx={{ fontSize: 18 }} />,
      label: "Disambiguation",
    };
  }
  if (n.includes("verif") || n.includes("anchor")) {
    return {
      color: "#2e7d32",
      bg: "#e8f5e9",
      icon: <VerifiedIcon sx={{ fontSize: 18 }} />,
      label: "Verification",
    };
  }
  if (
    n.includes("episode") ||
    n.includes("consolid") ||
    n.includes("builder")
  ) {
    return {
      color: "#00695c",
      bg: "#e0f2f1",
      icon: <MergeTypeIcon sx={{ fontSize: 18 }} />,
      label: "Episode builder",
    };
  }
  if (n.includes("label")) {
    return {
      color: "#f57f17",
      bg: "#fff8e1",
      icon: <CategoryIcon sx={{ fontSize: 18 }} />,
      label: "Labelling",
    };
  }
  return {
    color: "#37474f",
    bg: "#eceff1",
    icon: <BuildIcon sx={{ fontSize: 18 }} />,
    label: "General",
  };
}

// Convenience wrapper so call sites that have a PromptConfig can pass
// both name and description without restructuring args at every site.
function categoriseFromPrompt(p: PromptConfig): PromptCategory {
  return categorise(p.name, p.description);
}

function humanName(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const CATEGORY_ALL = "All";

// -- Stats -------------------------------------------------------------------

function computeStats(prompts: PromptConfig[]): StatTile[] {
  const total = prompts.length;
  const categories = new Set(
    prompts.map((p) => categoriseFromPrompt(p).label),
  ).size;
  const withDoubleCheck = prompts.filter((p) => p.verification).length;
  const withExamples = prompts.filter((p) => p.fewShotCount > 0).length;
  return [
    { id: "total", label: "Instruction sets", value: total, tone: "neutral" },
    {
      id: "categories",
      label: "Categories covered",
      value: categories,
      tone: "neutral",
    },
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

// -- Row helpers -------------------------------------------------------------

function promptTitle(p: PromptConfig): React.ReactNode {
  const cat = categoriseFromPrompt(p);
  return (
    <Stack direction="row" alignItems="center" spacing={1.25}>
      <Box
        component="span"
        aria-hidden="true"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 28,
          height: 28,
          borderRadius: "50%",
          bgcolor: cat.bg,
          color: cat.color,
          flexShrink: 0,
          "& svg": { fontSize: 16 },
        }}
      >
        {cat.icon}
      </Box>
      <Box component="span" sx={{ fontWeight: 600 }}>
        {humanName(p.name)}
      </Box>
    </Stack>
  );
}

function promptMeta(p: PromptConfig): React.ReactNode {
  const date = formatDate(p.updatedAt);
  const description =
    p.description?.trim() || "No description yet -- click to add one.";
  return (
    <>
      <Box
        component="span"
        sx={{
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          maxWidth: 640,
          fontStyle: p.description?.trim() ? "normal" : "italic",
          opacity: p.description?.trim() ? 1 : 0.7,
        }}
      >
        {description}
      </Box>
      {date ? <Box component="span">Updated {date}</Box> : null}
    </>
  );
}

function promptChips(p: PromptConfig): React.ReactNode {
  const cat = categoriseFromPrompt(p);
  return (
    <>
      <Chip
        size="small"
        label={cat.label}
        sx={{
          height: 22,
          fontSize: "0.7rem",
          bgcolor: cat.bg,
          color: cat.color,
          border: `1px solid ${cat.color}33`,
        }}
      />
      <Chip
        size="small"
        variant="outlined"
        label={`v${p.version}`}
        sx={{ height: 22, fontSize: "0.7rem", borderColor: "divider" }}
      />
      {p.verification ? (
        <Tooltip title="A second AI check runs after the first to confirm accuracy">
          <Chip
            size="small"
            color="success"
            icon={
              <CheckCircleOutlineIcon
                sx={{ fontSize: "14px !important" }}
              />
            }
            label="Double-check"
            sx={{ height: 22, fontSize: "0.7rem" }}
          />
        </Tooltip>
      ) : null}
      {p.fewShotCount > 0 ? (
        <Chip
          size="small"
          color="info"
          variant="outlined"
          label={`${p.fewShotCount} example${p.fewShotCount !== 1 ? "s" : ""}`}
          sx={{ height: 22, fontSize: "0.7rem" }}
        />
      ) : null}
    </>
  );
}

function promptActions(): React.ReactNode {
  return (
    <ChevronRightIcon
      aria-hidden="true"
      sx={{ color: "text.disabled", fontSize: 22 }}
    />
  );
}

function toReviewItem(
  p: PromptConfig,
  onSelect: (id: string) => void,
): ReviewListItem {
  return {
    id: p.id,
    title: promptTitle(p),
    meta: promptMeta(p),
    chips: promptChips(p),
    actions: promptActions(),
    onSelect: () => onSelect(p.id),
    tone: "neutral",
  };
}

// -- Skeleton ----------------------------------------------------------------

function SkeletonList() {
  return (
    <Stack spacing={1} data-testid="prompts-skeleton-list">
      {Array.from({ length: 6 }).map((_, i) => (
        <Box
          key={i}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            p: 2,
          }}
        >
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
            <Skeleton variant="circular" width={28} height={28} />
            <Skeleton width="40%" height={20} />
          </Stack>
          <Skeleton width="80%" height={14} sx={{ mb: 0.5 }} />
          <Skeleton width="55%" height={14} sx={{ mb: 1 }} />
          <Stack direction="row" spacing={0.75}>
            <Skeleton width={80} height={20} variant="rounded" />
            <Skeleton width={50} height={20} variant="rounded" />
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}

// -- Page --------------------------------------------------------------------

export default function PromptsPage() {
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>(CATEGORY_ALL);

  useEffect(() => {
    api
      .get<{ prompts: PromptConfig[] }>("/api/prompts")
      .then((d) => setPrompts(d.prompts || []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  }, []);

  const allCategories = useMemo(() => {
    const cats = Array.from(
      new Set(prompts.map((p) => categoriseFromPrompt(p).label)),
    ).sort();
    return [CATEGORY_ALL, ...cats];
  }, [prompts]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const f = prompts.filter((p) => {
      const matchCat =
        activeCategory === CATEGORY_ALL ||
        categoriseFromPrompt(p).label === activeCategory;
      const matchSearch =
        !q ||
        humanName(p.name).toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q);
      return matchCat && matchSearch;
    });
    return sortByIsoDateDesc(f, (p) => p.updatedAt);
  }, [prompts, activeCategory, search]);

  const grouped = useMemo(() => {
    const map = filtered.reduce<Record<string, PromptConfig[]>>((acc, p) => {
      const cat = categoriseFromPrompt(p).label;
      (acc[cat] ??= []).push(p);
      return acc;
    }, {});
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  const isFiltering = search.trim() !== "" || activeCategory !== CATEGORY_ALL;
  const stats = useMemo(() => computeStats(prompts), [prompts]);

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
    () =>
      allCategories.map((cat) => {
        const count =
          cat === CATEGORY_ALL
            ? prompts.length
            : prompts.filter(
                (p) => categoriseFromPrompt(p).label === cat,
              ).length;
        return { id: cat, label: cat, count };
      }),
    [allCategories, prompts],
  );

  const handleSelect = (id: string): void => {
    router.push(`/admin/prompts/${id}`);
  };

  return (
    <Box>
      <StatHero stats={stats} />

      <Box sx={{ mb: 2, mt: 2 }}>
        <FilterBar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Search by name or description"
          aria-label="Search AI instructions"
          trailing={<ToolbarActions actions={toolbarActions} />}
        />
        {!loading && allCategories.length > 1 ? (
          <Box sx={{ mt: 1.5 }}>
            <SegmentedTabs
              tabs={segmentedTabs}
              value={activeCategory}
              onChange={setActiveCategory}
              aria-label="Filter AI instructions by category"
            />
          </Box>
        ) : null}
        {!loading && prompts.length > 0 ? (
          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ display: "block", mt: 1 }}
          >
            {filtered.length} of {prompts.length} instruction set
            {prompts.length !== 1 ? "s" : ""}
          </Typography>
        ) : null}
      </Box>

      {loading ? (
        <SkeletonList />
      ) : prompts.length === 0 ? (
        <Box
          data-testid="prompts-empty"
          sx={{
            textAlign: "center",
            py: 10,
            px: 3,
            border: "2px dashed",
            borderColor: "divider",
            borderRadius: 3,
          }}
        >
          <TuneIcon
            sx={{ fontSize: 56, color: "text.disabled", mb: 1.5 }}
          />
          <Typography variant="h6" gutterBottom fontWeight={700}>
            No instructions yet
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 3, maxWidth: 480, mx: "auto" }}
          >
            Add your first set of AI instructions to get the pipeline
            working.
          </Typography>
        </Box>
      ) : filtered.length === 0 ? (
        <Box
          data-testid="prompts-no-match"
          sx={{
            textAlign: "center",
            py: 8,
            px: 3,
            border: "2px dashed",
            borderColor: "divider",
            borderRadius: 3,
          }}
        >
          <SearchIcon
            sx={{ fontSize: 48, color: "text.disabled", mb: 1.5 }}
          />
          <Typography variant="h6" gutterBottom fontWeight={700}>
            No matches
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 2, maxWidth: 480, mx: "auto" }}
          >
            Try a different search term or pick a different category.
          </Typography>
        </Box>
      ) : isFiltering ? (
        <ReviewListCard
          items={filtered.map((p) => toReviewItem(p, handleSelect))}
        />
      ) : (
        <Stack spacing={3} data-testid="prompts-grouped">
          {grouped.map(([groupLabel, items]) => {
            const cat = categoriseFromPrompt(items[0]);
            return (
              <Box key={groupLabel}>
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={1}
                  sx={{ mb: 1 }}
                >
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      bgcolor: cat.bg,
                      color: cat.color,
                    }}
                    aria-hidden="true"
                  >
                    {cat.icon}
                  </Box>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {groupLabel}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    {items.length} instruction
                    {items.length !== 1 ? "s" : ""}
                  </Typography>
                </Stack>
                <ReviewListCard
                  items={items.map((p) => toReviewItem(p, handleSelect))}
                />
              </Box>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
