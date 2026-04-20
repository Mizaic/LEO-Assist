"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { bindEntraGroup, type EntraGroup } from "@/lib/api/admin";

interface Props {
  group: EntraGroup;
  roleNames: string[];
  onClose: () => void;
  onBound: () => void;
}

function friendlyRole(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function BindGroupDialog({ group, roleNames, onClose, onBound }: Props) {
  const [roleName, setRoleName] = useState<string>("");
  const [confirmName, setConfirmName] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = confirmName.trim();
  const matchesName = trimmed.length > 0 && trimmed === group.displayName.trim();
  const canSubmit = roleName !== "" && matchesName && !submitting;

  const handleBind = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await bindEntraGroup(group.id, {
        display_name: group.displayName,
        name: group.displayName,
        role_name: roleName,
        description: group.description ?? "",
        confirm_display_name: trimmed,
      });
      onBound();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not bind this group.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onClose={submitting ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Bind &ldquo;{group.displayName}&rdquo; to a LEO role</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Members of this Entra security group will receive the LEO role you
          choose below the next time they sign in. To prevent mistakes, please
          re-type the group&rsquo;s exact name to confirm.
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>LEO role</InputLabel>
          <Select
            value={roleName}
            label="LEO role"
            onChange={(e) => setRoleName(e.target.value)}
          >
            {roleNames.map((r) => (
              <MenuItem key={r} value={r}>
                {friendlyRole(r)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          fullWidth
          size="small"
          label="Type the group name to confirm"
          placeholder={group.displayName}
          value={confirmName}
          onChange={(e) => setConfirmName(e.target.value)}
          error={confirmName.length > 0 && !matchesName}
          helperText={
            confirmName.length === 0
              ? "Must match exactly."
              : matchesName
              ? "Looks good."
              : "The name does not match yet."
          }
          sx={{ mb: 2 }}
        />
        {error && <Alert severity="error">{error}</Alert>}
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Object id: {group.id}
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleBind}
          disabled={!canSubmit}
        >
          {submitting ? "Binding..." : "Bind group"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
