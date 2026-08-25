/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59, DI-6BD7B681
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";

import {
  TaskQueue,
  type CountsBySource,
  type WorkTask,
  type WorkTaskType,
} from "@leo/design-system";

import AreaIntro from "@/components/AreaIntro";
import WorkTaskDialog from "./WorkTaskDialog";

interface WorkPageResponse {
  tasks: WorkTask[];
  counts_by_source: CountsBySource;
  limit: number;
  offset: number;
}

const EMPTY_COUNTS: CountsBySource = {
  coding_review: 0,
  safety_net_alert: 0,
  gold_label: 0,
  extraction_quality_pause: 0,
  surface_form_approval: 0,
  phrase_publish: 0,
};

async function fetchWorkTasks(
  activeSources: ReadonlyArray<WorkTaskType>,
): Promise<WorkPageResponse> {
  const qs = new URLSearchParams();
  activeSources.forEach((s) => qs.append("source", s));
  qs.set("limit", "100");
  qs.set("offset", "0");
  const res = await fetch("/api/work/tasks?" + qs.toString(), {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Failed to load work tasks (" + res.status + ")");
  }
  return (await res.json()) as WorkPageResponse;
}

export default function WorkPage() {
  const [tasks, setTasks] = useState<WorkTask[]>([]);
  const [counts, setCounts] = useState<CountsBySource>(EMPTY_COUNTS);
  const [activeSources, setActiveSources] = useState<WorkTaskType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<WorkTask | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchWorkTasks(activeSources);
      setTasks(payload.tasks);
      setCounts(payload.counts_by_source);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not load tasks.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [activeSources]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleSource = useCallback((source: WorkTaskType) => {
    setActiveSources((prev) => {
      if (prev.includes(source)) {
        return prev.filter((s) => s !== source);
      }
      return [...prev, source];
    });
  }, []);

  return (
    <Box
      component="main"
      sx={{ px: { xs: 2, md: 4 }, py: 3, maxWidth: 1000, mx: "auto" }}
    >
      <Stack spacing={2}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 600 }}>
          My work
        </Typography>
        <AreaIntro area="work" />
        {error ? (
          <Alert severity="error" data-testid="work-error">
            {error}
          </Alert>
        ) : null}
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={28} />
          </Box>
        ) : (
          <TaskQueue
            tasks={tasks}
            countsBySource={counts}
            activeSources={activeSources}
            onToggleSource={toggleSource}
            onSelectTask={setSelectedTask}
          />
        )}
        <WorkTaskDialog
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onResolved={() => {
            setSelectedTask(null);
            void refresh();
          }}
        />
      </Stack>
    </Box>
  );
}
