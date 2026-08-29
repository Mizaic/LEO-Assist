/**
 * Edit a person: name, admin, organisations, groups, and old roles.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-35D11EED")
 */
"use client";

import { useState } from "react";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { patchUser, type Group, type User } from "@/lib/api/admin";

interface OrgOption {
  id: string;
  name: string;
}

interface Props {
  user: User;
  orgs: OrgOption[];
  groups: Group[];
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}

export default function UserEditDialog({
  user,
  orgs,
  groups,
  onClose,
  onSaved,
  onError,
}: Props) {
  const [name, setName] = useState(user.name || "");
  const [isAdmin, setIsAdmin] = useState(Boolean(user.is_platform_admin));
  const [orgIds, setOrgIds] = useState<string[]>(user.org_ids || []);
  const [groupIds, setGroupIds] = useState<string[]>(
    (user.groups || []).map((g) => g.id)
  );
  const [clearLegacy, setClearLegacy] = useState(false);
  const [saving, setSaving] = useState(false);
  const hasLegacy = (user.legacy_roles || []).length > 0;

  const handleSave = async () => {
    setSaving(true);
    try {
      await patchUser(user.email, {
        name: name.trim() || user.email,
        is_platform_admin: isAdmin,
        org_ids: orgIds,
        group_ids: groupIds,
        clear_legacy_roles: clearLegacy,
      });
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not save this person.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Edit person</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Change this person&apos;s name, organisations, and groups. Groups
          give them their roles.
        </Typography>
        <TextField
          fullWidth
          label="Full name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
          {user.email}
        </Typography>
        <FormControlLabel
          control={
            <Switch checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
          }
          label="Platform admin"
          sx={{ mb: 1 }}
        />
        <Divider sx={{ my: 1.5 }} />
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Organisations they can see</InputLabel>
          <Select
            multiple
            value={orgIds}
            label="Organisations they can see"
            onChange={(e) => setOrgIds(e.target.value as string[])}
            renderValue={(sel) =>
              (sel as string[])
                .map((id) => orgs.find((o) => o.id === id)?.name ?? id)
                .join(", ")
            }
          >
            {orgs.map((o) => (
              <MenuItem key={o.id} value={o.id}>
                {o.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Groups</InputLabel>
          <Select
            multiple
            value={groupIds}
            label="Groups"
            onChange={(e) => setGroupIds(e.target.value as string[])}
            renderValue={(sel) =>
              (sel as string[])
                .map((id) => groups.find((g) => g.id === id)?.name ?? id)
                .join(", ")
            }
          >
            {groups.map((g) => (
              <MenuItem key={g.id} value={g.id}>
                {g.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {hasLegacy && (
          <FormControlLabel
            control={
              <Checkbox
                checked={clearLegacy}
                onChange={(e) => setClearLegacy(e.target.checked)}
              />
            }
            label="Remove old role schema (direct roles from before groups)"
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          data-testid="people-edit-save"
        >
          {saving ? "Saving..." : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
