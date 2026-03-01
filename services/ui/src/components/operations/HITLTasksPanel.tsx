"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";

interface HITLTask {
  task_id: string;
  task_type: string;
  episode_id: string;
  patient_id: string;
  status: string;
  priority: number;
  reason: string;
  created_at: string;
  updated_at: string;
}

interface ResolvePayload {
  status: "resolved" | "dismissed" | "escalated";
  resolution: string;
  resolved_by: string;
}

const STATUS_COLOURS: Record<string, "warning" | "success" | "error" | "default"> = {
  pending: "warning",
  resolved: "success",
  dismissed: "default",
  escalated: "error",
};

const EXCLUSION_STAGES: TabStage[] = [
  {
    id: "ex1", num: 1,
    label: "Conflict Found",
    tooltip: "The system spots a problem with a patient's exclusion -- for example, a rule was applied that may not be correct for this patient.",
    detailIn: "Patient episode data and exclusion rules",
    detailOut: "A conflict record that needs a human to check",
  },
  {
    id: "ex2", num: 2,
    label: "Task Created",
    tooltip: "A task is added to this queue so a reviewer can look at it. It is given a priority number -- higher priority means it needs checking first.",
    detailIn: "The conflict record",
    detailOut: "A task in the queue with a reason and priority",
  },
  {
    id: "ex3", num: 3,
    label: "You Review It",
    tooltip: "You open the task and read the reason the system flagged it. You can see the patient, the episode, and what went wrong.",
    detailIn: "The task with patient and episode details",
    detailOut: "Your understanding of the conflict",
  },
  {
    id: "ex4", num: 4,
    label: "You Decide",
    tooltip: "You pick one of three outcomes: resolved (fixed), dismissed (not a real problem), or escalated (needs senior review).",
    detailIn: "Your decision and a short note explaining it",
    detailOut: "An outcome: resolved, dismissed, or escalated",
    branches: [
      {
        label: "Escalated",
        description: "If you escalate, the task stays flagged for a senior reviewer to look at",
      },
    ],
  },
  {
    id: "ex5", num: 5,
    label: "Case Closed",
    tooltip: "The outcome and your notes are saved. The task is removed from the pending queue and logged for audit.",
    detailIn: "Your decision and reviewer ID",
    detailOut: "A closed task saved to the audit log",
  },
];

const PEER_REVIEW_STAGES: TabStage[] = [
  {
    id: "pr1", num: 1,
    label: "1 in 10 Chosen",
    tooltip: "One in every ten coded notes is picked at random for a second opinion. This is a mandatory quality check.",
    detailIn: "All approved coding outputs from the pipeline",
    detailOut: "A random 10% sample selected for review",
  },
  {
    id: "pr2", num: 2,
    label: "Task Created",
    tooltip: "A peer review task is added to this queue for a second reviewer to check. It includes the note and the original coding.",
    detailIn: "The sampled coding output",
    detailOut: "A peer review task in the queue",
  },
  {
    id: "pr3", num: 3,
    label: "Second Opinion",
    tooltip: "A different person (not the original coder) reads the note and the coding to check if it looks right.",
    detailIn: "The original coded note and the reviewer's judgement",
    detailOut: "Agreement or a flag that something needs fixing",
  },
  {
    id: "pr4", num: 4,
    label: "They Agree or Flag",
    tooltip: "The reviewer marks the coding as correct, or flags a problem with a short note explaining what is wrong.",
    detailIn: "The reviewer's notes",
    detailOut: "A resolved outcome or an escalation",
    branches: [
      {
        label: "Problem found",
        description: "If a mistake is found, the task can be escalated for correction before the data is used",
      },
    ],
  },
  {
    id: "pr5", num: 5,
    label: "Quality Logged",
    tooltip: "The result is saved. It counts towards the overall quality audit for the pipeline.",
    detailIn: "The peer review outcome",
    detailOut: "A closed task saved to the audit log",
  },
];

const STAGE_CONFIG: Record<string, { stages: TabStage[]; color: string; lightColor: string; label: string }> = {
  exclusion_conflict: {
    stages: EXCLUSION_STAGES,
    color: "#F59E0B",
    lightColor: "#FFFBEB",
    label: "Exclusion Conflicts",
  },
  peer_review: {
    stages: PEER_REVIEW_STAGES,
    color: "#6366F1",
    lightColor: "#EEF2FF",
    label: "Peer Review",
  },
};

export default function HITLTasksPanel({
  taskType,
  title,
  description,
}: {
  taskType: string;
  title: string;
  description: string;
}) {
  const [tasks, setTasks] = useState<HITLTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HITLTask | null>(null);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolvePayload, setResolvePayload] = useState<ResolvePayload>({
    status: "resolved",
    resolution: "",
    resolved_by: "",
  });
  const [resolving, setResolving] = useState(false);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/operations/tasks?task_type=${taskType}&status=pending&limit=200`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTasks(data.tasks ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [taskType]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const handleResolve = async () => {
    if (!selected) return;
    setResolving(true);
    try {
      const res = await fetch(
        `/api/operations/tasks/${selected.task_id}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(resolvePayload),
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setResolveOpen(false);
      await fetchTasks();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to resolve task");
    } finally {
      setResolving(false);
    }
  };

  const diagramConfig = STAGE_CONFIG[taskType];

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", px: 3, py: 3 }}>
      {/* How this works */}
      {diagramConfig && (
        <Accordion variant="outlined" disableGutters sx={{ mb: 3 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              How this tab works
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            <TabFlowDiagram
              stages={diagramConfig.stages}
              color={diagramConfig.color}
              lightColor={diagramConfig.lightColor}
              trackLabel={diagramConfig.label}
            />
          </AccordionDetails>
        </Accordion>
      )}

      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
        <Box>
          <Typography variant="h6" fontWeight={600}>
            {title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </Box>
        <Button variant="outlined" size="small" onClick={fetchTasks} disabled={loading}>
          Refresh
        </Button>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : tasks.length === 0 ? (
        <Alert severity="success">No pending tasks in this queue.</Alert>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Task ID</TableCell>
              <TableCell>Patient</TableCell>
              <TableCell>Episode</TableCell>
              <TableCell>Reason</TableCell>
              <TableCell>Priority</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {tasks.map((t) => (
              <TableRow key={t.task_id} hover>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 11 }}>
                  {t.task_id.slice(0, 8)}…
                </TableCell>
                <TableCell>{t.patient_id}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 11 }}>
                  {(t.episode_id ?? "").slice(0, 8)}…
                </TableCell>
                <TableCell sx={{ maxWidth: 300, whiteSpace: "normal" }}>
                  {t.reason}
                </TableCell>
                <TableCell>{t.priority}</TableCell>
                <TableCell>
                  <Chip
                    label={t.status}
                    size="small"
                    color={STATUS_COLOURS[t.status] ?? "default"}
                  />
                </TableCell>
                <TableCell sx={{ fontSize: 11 }}>
                  {t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}
                </TableCell>
                <TableCell>
                  <Button
                    size="small"
                    variant="contained"
                    disableElevation
                    onClick={() => {
                      setSelected(t);
                      setResolvePayload({ status: "resolved", resolution: "", resolved_by: "" });
                      setResolveOpen(true);
                    }}
                  >
                    Review
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Resolve dialog */}
      <Dialog open={resolveOpen} onClose={() => setResolveOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Resolve Task</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <Typography variant="body2" color="text.secondary">
              <strong>Reason:</strong> {selected?.reason}
            </Typography>
            <Select
              size="small"
              value={resolvePayload.status}
              onChange={(e) =>
                setResolvePayload((p) => ({
                  ...p,
                  status: e.target.value as ResolvePayload["status"],
                }))
              }
            >
              <MenuItem value="resolved">Resolved</MenuItem>
              <MenuItem value="dismissed">Dismissed</MenuItem>
              <MenuItem value="escalated">Escalated</MenuItem>
            </Select>
            <TextField
              label="Resolution notes"
              multiline
              rows={3}
              size="small"
              value={resolvePayload.resolution}
              onChange={(e) =>
                setResolvePayload((p) => ({ ...p, resolution: e.target.value }))
              }
            />
            <TextField
              label="Reviewer ID"
              size="small"
              value={resolvePayload.resolved_by}
              onChange={(e) =>
                setResolvePayload((p) => ({ ...p, resolved_by: e.target.value }))
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResolveOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleResolve}
            disabled={resolving || !resolvePayload.resolution || !resolvePayload.resolved_by}
          >
            {resolving ? <CircularProgress size={16} /> : "Submit"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
