"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Publish dialog for the audit template editor.
 * Supports per-org publish (Autocomplete from session orgs) and
 * a global "publish to all organisations" toggle for platform admins.
 */

import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Divider from "@mui/material/Divider";
import CircularProgress from "@mui/material/CircularProgress";

import { publishTemplate, type PublishTemplatePayload } from "@/lib/auditTemplateApi";
import { useOrg } from "@/context/OrgContext";
import type { OrgInfo } from "@/lib/authContext";

interface PublishDialogProps {
  templateId: string;
  templateTitle: string;
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
}

function orgLabel(o: OrgInfo): string {
  return o.odsCode ? `${o.name} (${o.odsCode})` : o.name;
}

export default function PublishDialog({
  templateId,
  templateTitle,
  open,
  onClose,
  onPublished,
}: PublishDialogProps) {
  const { organizations, isPlatformAdmin } = useOrg();
  const [publishAll, setPublishAll] = useState(false);
  const [selectedOrgs, setSelectedOrgs] = useState<OrgInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canPublish = publishAll || selectedOrgs.length > 0;

  const handlePublish = async () => {
    setSaving(true);
    setError(null);
    try {
      if (publishAll) {
        const payload: PublishTemplatePayload = {
          template_id: templateId,
          scope_type: "global",
          scope_id: "__global__",
        };
        await publishTemplate(templateId, payload);
      } else {
        await Promise.all(
          selectedOrgs.map((o) =>
            publishTemplate(templateId, {
              template_id: templateId,
              scope_type: "org",
              scope_id: o.id,
            }),
          ),
        );
      }
      onPublished();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Publish template</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <Typography variant="body2">
          Publishing <strong>{templateTitle}</strong> makes it visible on the
          Clinical Audit page for the selected organisations.
        </Typography>

        {isPlatformAdmin && (
          <>
            <FormControlLabel
              control={
                <Switch
                  checked={publishAll}
                  onChange={(_, v) => {
                    setPublishAll(v);
                    if (v) setSelectedOrgs([]);
                  }}
                  inputProps={{ "aria-label": "Publish to all organisations" }}
                />
              }
              label="Publish to all organisations"
            />
            {publishAll && (
              <Alert severity="warning" sx={{ fontSize: 12 }}>
                This will set the global default. Any org without its own
                assignment will show this template.
              </Alert>
            )}
            <Divider flexItem />
          </>
        )}

        {!publishAll && (
          <Autocomplete
            multiple
            options={organizations}
            getOptionLabel={orgLabel}
            value={selectedOrgs}
            onChange={(_, v) => setSelectedOrgs(v)}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Select organisations"
                size="small"
                placeholder={selectedOrgs.length === 0 ? "Search by name or ODS code..." : ""}
              />
            )}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            noOptionsText="No organisations found"
          />
        )}

        {error && <Alert severity="error">{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handlePublish}
          disabled={!canPublish || saving}
          startIcon={saving ? <CircularProgress size={14} /> : undefined}
        >
          Publish
        </Button>
      </DialogActions>
    </Dialog>
  );
}
