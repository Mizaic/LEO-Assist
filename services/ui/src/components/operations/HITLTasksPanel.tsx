"use client";

import { useCallback, useEffect, useState } from "react";
import {
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

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", px: 3 }}>
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
