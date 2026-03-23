"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ReviewSection from "@/components/operations/ReviewSection";

export default function OperationsReviewsPage() {
  const [msg, setMsg] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);

  async function clearResolved() {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/training/coding-review/resolved", { method: "DELETE" });
      if (!res.ok) throw new Error(`${res.status}`);
      const body = await res.json();
      setMsg(`Cleared ${body.deleted ?? 0} resolved review items.`);
      setRefreshKey((k) => k + 1);
    } catch {
      setMsg("Could not clear resolved review items.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAll() {
    setDeleteAllOpen(false);
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/training/review-queue/all", { method: "DELETE" });
      if (!res.ok) throw new Error(`${res.status}`);
      const body = await res.json();
      const total = body.total_deleted ?? 0;
      setMsg(`Deleted all ${total} items from the queue.`);
      setRefreshKey((k) => k + 1);
    } catch {
      setMsg("Could not delete queue items.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Things to check
        </Typography>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" onClick={clearResolved} disabled={busy}>
            Clear resolved
          </Button>
          <Button
            variant="outlined"
            color="error"
            size="small"
            onClick={() => setDeleteAllOpen(true)}
            disabled={busy}
          >
            Delete all
          </Button>
        </Stack>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Review coding, context, HITL and surface-form tasks.
      </Typography>
      {msg && (
        <Alert sx={{ mb: 2 }} severity={msg.startsWith("Cleared") || msg.startsWith("Deleted") ? "success" : "error"}>
          {msg}
        </Alert>
      )}
      <ReviewSection refreshKey={refreshKey} />

      <Dialog open={deleteAllOpen} onClose={() => setDeleteAllOpen(false)}>
        <DialogTitle>Delete all queue items?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will remove every item in the queue (coding reviews, surface form tasks, and HITL tasks).
            Use this when clearing items from an old pipeline. This cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteAllOpen(false)}>Cancel</Button>
          <Button onClick={deleteAll} color="error" variant="contained">
            Delete all
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

