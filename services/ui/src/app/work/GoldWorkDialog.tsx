/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import type { WorkTask } from "@leo/design-system";
import { GoldLabelDetailDialog } from "@/components/gold-dataset/GoldDatasetPanel";
import { workJson } from "./workJson";
import { workTaskSourceId } from "./workTaskSourceId";

interface GoldLabelItem {
  label_id: string;
  text: string;
  entities_json: string | null;
  quality_score: number | null;
  source: string;
  verified_by: string | null;
  verified_at: string | null;
  candidate_id: string | null;
  updated_at: string;
}

interface Props {
  task: WorkTask;
  onClose: () => void;
  onResolved: () => void;
}

export default function GoldWorkDialog({ task, onClose, onResolved }: Props) {
  const sourceId = workTaskSourceId(task.task_id);
  const [item, setItem] = useState<GoldLabelItem | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setError("");
    workJson<GoldLabelItem>(
      "/api/training/gold-labels/by-candidate/" +
        encodeURIComponent(sourceId) +
        "/ensure",
      { method: "POST" },
    )
      .then((row) => {
        if (!cancelled) setItem(row);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this label. Try again.");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  if (item) {
    return (
      <GoldLabelDetailDialog
        item={item}
        onClose={onClose}
        onMarkGold={onResolved}
        onEntitiesChanged={onResolved}
      />
    );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      data-testid="work-task-dialog"
    >
      <DialogTitle sx={{ pr: 6 }}>
        {task.summary}
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {!error ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={28} aria-label="Loading" />
          </Box>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
