"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { TermSearchResult } from "@/lib/types";
import ReviewCard, {
  type ReviewItem,
  buildQuestion,
  buildExplanation,
} from "./ReviewCard";

// -- Fetch helpers -----------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

interface CodingGroup {
  entity_text: string;
  entity_label: string;
  review_count: number;
  best_score: number | null;
  sample_review_id: string;
  any_uncoded: boolean;
}

interface HitlTask {
  task_id: string;
  task_type: string;
  episode_id: string;
  patient_id: string;
  status: string;
  priority: number;
  reason: string;
}

function codingGroupToItem(g: CodingGroup): ReviewItem {
  const base: ReviewItem = {
    id: `coding:${g.entity_text}`,
    kind: "coding",
    entityText: g.entity_text,
    entityLabel: g.entity_label,
    count: g.review_count,
    confidence: g.best_score,
    uncoded: g.any_uncoded,
    question: "",
    explanation: "",
  };
  base.question = buildQuestion(base);
  base.explanation = buildExplanation(base);
  return base;
}

function hitlTaskToItem(t: HitlTask): ReviewItem {
  const base: ReviewItem = {
    id: `hitl:${t.task_id}`,
    kind: "hitl",
    entityText: "",
    entityLabel: "",
    count: 1,
    confidence: null,
    uncoded: false,
    question: "",
    explanation: "",
    taskType: t.task_type,
    reason: t.reason,
  };
  base.question = buildQuestion(base);
  base.explanation = buildExplanation(base);
  return base;
}

// -- Component ---------------------------------------------------------------

interface Props {
  onStatsChange?: () => void;
}

type FilterKey = "all" | "coding" | "hitl";

export default function ReviewSection({ onStatsChange }: Props) {
  const [queue, setQueue] = useState<ReviewItem[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resolved, setResolved] = useState(0);
  const [filter, setFilter] = useState<FilterKey>("all");

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [codingRes, hitlRes] = await Promise.allSettled([
        jsonFetch<{ groups: CodingGroup[] }>(
          "/api/training/coding-review/grouped?page=1&page_size=50",
        ),
        jsonFetch<{ tasks: HitlTask[] }>(
          "/api/operations/tasks?status=pending",
        ),
      ]);

      const items: ReviewItem[] = [];
      if (codingRes.status === "fulfilled") {
        items.push(...codingRes.value.groups.map(codingGroupToItem));
      }
      if (hitlRes.status === "fulfilled") {
        items.push(...hitlRes.value.tasks.map(hitlTaskToItem));
      }

      items.sort((a, b) => b.count - a.count);
      setQueue(items);
      setIndex(0);
      setResolved(0);
    } catch {
      setError("Could not load review items. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  const filtered = queue.filter(
    (item) => filter === "all" || item.kind === filter,
  );

  const current = filtered[index] ?? null;
  const total = filtered.length;
  const pct = total > 0 ? Math.round((resolved / (resolved + total)) * 100) : 0;

  const advance = useCallback(() => {
    setQueue((prev) => prev.filter((_, i) => i !== queue.indexOf(current!)));
    setResolved((r) => r + 1);
    setIndex(0);
    onStatsChange?.();
  }, [current, queue, onStatsChange]);

  const handleResolveCoding = useCallback(
    async (item: ReviewItem, result: TermSearchResult) => {
      setBusy(true);
      try {
        await jsonFetch("/api/training/coding-review/batch-resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            entity_text: item.entityText,
            resolved_concept_id: result.snomed_concept_id,
            resolved_term: result.term,
            reviewer: "operations_ui",
          }),
        });
        advance();
      } catch {
        setError("Could not save. Please try again.");
      } finally {
        setBusy(false);
      }
    },
    [advance],
  );

  const handleResolveHitl = useCallback(
    async (item: ReviewItem, status: "resolved" | "dismissed") => {
      const taskId = item.id.replace("hitl:", "");
      setBusy(true);
      try {
        await jsonFetch(`/api/operations/tasks/${taskId}/resolve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status,
            resolution: status === "resolved" ? "Approved" : "Dismissed",
            resolved_by: "operations_ui",
          }),
        });
        advance();
      } catch {
        setError("Could not save. Please try again.");
      } finally {
        setBusy(false);
      }
    },
    [advance],
  );

  const handleSkip = useCallback(() => {
    if (index < total - 1) setIndex((i) => i + 1);
    else setIndex(0);
  }, [index, total]);

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "s" || e.key === "S") handleSkip();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleSkip]);

  // -- Render ----------------------------------------------------------------

  if (loading) {
    return (
      <Stack gap={2}>
        <Skeleton height={8} />
        <Skeleton variant="rounded" height={200} />
      </Stack>
    );
  }

  return (
    <Stack gap={2}>
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      {/* Progress */}
      <Box>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            {total > 0
              ? `${resolved} done -- ${total} left to review`
              : "All caught up"}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {pct}%
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={pct}
          aria-label="Review progress"
        />
      </Box>

      {/* Filters */}
      <Stack direction="row" gap={0.75}>
        {(["all", "coding", "hitl"] as FilterKey[]).map((key) => {
          const labels: Record<FilterKey, string> = {
            all: "All",
            coding: "Coding",
            hitl: "Tasks",
          };
          const count =
            key === "all"
              ? queue.length
              : queue.filter((i) => i.kind === key).length;
          return (
            <Chip
              key={key}
              label={`${labels[key]} (${count})`}
              size="small"
              variant={filter === key ? "filled" : "outlined"}
              color={filter === key ? "primary" : "default"}
              onClick={() => {
                setFilter(key);
                setIndex(0);
              }}
            />
          );
        })}
      </Stack>

      {/* Card */}
      {current ? (
        <ReviewCard
          item={current}
          onResolveCoding={handleResolveCoding}
          onResolveHitl={handleResolveHitl}
          onSkip={handleSkip}
          busy={busy}
        />
      ) : (
        <Card sx={{ p: 4, textAlign: "center" }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Nothing to review right now
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Run a pipeline to generate new items, or check back later.
          </Typography>
        </Card>
      )}

      {/* Keyboard hint */}
      {current && (
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ textAlign: "center" }}
        >
          Press S to skip
        </Typography>
      )}
    </Stack>
  );
}

