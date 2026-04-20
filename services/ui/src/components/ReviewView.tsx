/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-F8631A82
 *   DI: DI-1B8AC856
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8631A82")
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { fetchTaskDetail } from "@/lib/api";

interface Props {
  taskId: string;
  patientId: string;
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

export default function ReviewView({ taskId, patientId }: Props) {
  void patientId;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [rejectOpen, setRejectOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await fetchTaskDetail(taskId);
        if (!cancelled) setDetail(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load task");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "r") return;
      if (isInteractiveTarget(event.target)) return;
      setRejectOpen(true);
    };
    document.body.addEventListener("keydown", onKeyDown);
    return () => document.body.removeEventListener("keydown", onKeyDown);
  }, []);

  if (loading) {
    return (
      <Box aria-label="Loading" sx={{ display: "flex", justifyContent: "center", p: 3 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!detail?.candidate) {
    return (
      <Box>
        <Alert severity="info">No candidate data available for this task.</Alert>
        <Button sx={{ mt: 2 }}>Return to encounters</Button>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h6">{`Review: ${detail.task?.encounter_id ?? ""}`}</Typography>
      <TextField
        label="Decision reason"
        placeholder="Reason (required for Reject)"
        size="small"
        sx={{ mt: 2 }}
      />
      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)}>
        <DialogTitle>Reject this encounter?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">This decision requires a reason.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
          <Button color="error" onClick={() => setRejectOpen(false)}>Reject</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
