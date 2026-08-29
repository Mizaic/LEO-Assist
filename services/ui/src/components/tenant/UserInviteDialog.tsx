/**
 * Add a person to LEO.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
import EntraUserPicker from "@/components/tenant/EntraUserPicker";
import {
  assignUserRole,
  createUser,
  type EntraCapability,
  type Group,
} from "@/lib/api/admin";
import { friendlyRole } from "./userManagementHelpers";

interface OrgOption {
  id: string;
  name: string;
}

interface Props {
  orgs: OrgOption[];
  groups: Group[];
  roles: { name: string }[];
  entraCapability: EntraCapability | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}

export default function UserInviteDialog({
  orgs,
  groups,
  roles,
  entraCapability,
  onClose,
  onSaved,
  onError,
}: Props) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [orgIds, setOrgIds] = useState<string[]>([]);
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [role, setRole] = useState("");
  const [saving, setSaving] = useState(false);

  const handleInvite = async () => {
    if (!email.trim()) return;
    setSaving(true);
    try {
      const trimmed = email.trim().toLowerCase();
      await createUser({
        email: trimmed,
        name: name.trim() || trimmed,
        is_platform_admin: isAdmin,
        org_ids: orgIds,
        group_ids: groupIds,
      });
      if (role) await assignUserRole(trimmed, { role_name: role });
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not add this person.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add a person</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          They will be able to log in with this email. Groups give them their
          roles.
        </Typography>
        {entraCapability?.can_search_users ? (
          <Box sx={{ mb: 2 }}>
            <EntraUserPicker
              selectedEmail={email}
              helperText="Pick a person from Microsoft Entra. We'll fill in their name and email."
              onSelect={({ email: nextEmail, name: nextName }) => {
                setEmail(nextEmail);
                setName(nextName);
              }}
            />
          </Box>
        ) : null}
        <TextField
          fullWidth
          label="Email address"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
          helperText={
            entraCapability?.can_search_users ? "Or type an email manually." : undefined
          }
        />
        <TextField
          fullWidth
          label="Full name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
        />
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
        <FormControl fullWidth size="small">
          <InputLabel>Role</InputLabel>
          <Select
            value={role}
            label="Role"
            onChange={(e) => setRole(e.target.value)}
          >
            <MenuItem value="">No extra role</MenuItem>
            {roles.map((r) => (
              <MenuItem key={r.name} value={r.name}>
                {friendlyRole(r.name)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleInvite}
          disabled={saving || !email.trim()}
        >
          {saving ? "Adding..." : "Add person"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
