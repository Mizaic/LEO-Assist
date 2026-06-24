"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 */

import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { publishTemplate, type PublishTemplatePayload } from "@/lib/auditTemplateApi";

interface PublishDialogProps {
  templateId: string;
  templateTitle: string;
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
}

export default function PublishDialog({
  templateId,
  templateTitle,
  open,
  onClose,
  onPublished,
}: PublishDialogProps) {
  const [orgId, setOrgId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePublish = async () => {
    if (!orgId.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const payload: PublishTemplatePayload = {
        template_id: templateId,
        scope_type: "org",
        scope_id: orgId.trim(),
      };
      await publishTemplate(templateId, payload);
      onPublished();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Publish template</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <Typography variant="body2">
          You are about to publish <strong>{templateTitle}</strong> to an organisation. Clinical
          users in that organisation will see this template on the Clinical Audit page.
        </Typography>
        <TextField
          label="Organisation ID"
          size="small"
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
          helperText="The org ID this template should be assigned to"
          fullWidth
          autoFocus
        />
        {error && <Alert severity="error">{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handlePublish}
          disabled={!orgId.trim() || saving}
          startIcon={saving ? <CircularProgress size={14} /> : undefined}
        >
          Publish
        </Button>
      </DialogActions>
    </Dialog>
  );
}
