/**
 * Atlas trace:
 *   DI: DI-47D2CD86
 */
"use client";

import { useEffect, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";

import {
  fetchSurfaceFormAuditLog,
  type SurfaceFormAuditEntry,
} from "@/lib/api/legacy";

export function PhraseChangeLogDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [audit, setAudit] = useState<SurfaceFormAuditEntry[]>([]);

  useEffect(() => {
    if (!open) return;
    fetchSurfaceFormAuditLog(undefined, 100, 0)
      .then((page) => setAudit(page.items || []))
      .catch(() => setAudit([]));
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="phrase-audit-title">
      <DialogTitle id="phrase-audit-title">Change log</DialogTitle>
      <DialogContent>
        {audit.map((row) => (
          <p key={row.id} style={{ fontSize: 14 }}>
            {row.action} · {row.normalized}
            {row.detail ? ` -- ${row.detail}` : ""}
          </p>
        ))}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
