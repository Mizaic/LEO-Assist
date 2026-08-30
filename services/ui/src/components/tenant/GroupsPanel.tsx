/**
 * Groups list for Platform Management.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import ManageAccountsIcon from "@mui/icons-material/ManageAccounts";
import { type Group } from "@/lib/api/admin";

interface PanelProps {
  groups: Group[];
  onCreate: () => void;
  onMembers: (g: Group) => void;
  onDelete: (g: Group) => void;
}

export default function GroupsPanel({ groups, onCreate, onMembers, onDelete }: PanelProps) {
  return (
    <Grid size={{ xs: 12, lg: 5 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <GroupsOutlinedIcon color="action" fontSize="small" />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Groups</Typography>
          <Chip label={groups.length} size="small" />
        </Box>
        <Button variant="outlined" size="small" onClick={onCreate}>+ Create group</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Organise people by team or organisation.
      </Typography>
      {groups.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No groups yet. Create one to organise people.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {groups.map((g) => (
            <GroupRow key={g.id} group={g} onMembers={onMembers} onDelete={onDelete} />
          ))}
        </Stack>
      )}
    </Grid>
  );
}

function GroupRow({
  group: g, onMembers, onDelete,
}: {
  group: Group;
  onMembers: (g: Group) => void;
  onDelete: (g: Group) => void;
}) {
  return (
    <Paper variant="outlined" sx={{ px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.5 }}>
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }} noWrap>{g.name}</Typography>
        {g.org_name && (
          <Typography variant="caption" color="text.secondary">{g.org_name}</Typography>
        )}
      </Box>
      <Chip
        label={g.source === "entra" ? "Entra" : "Local"}
        size="small"
        color={g.source === "entra" ? "primary" : "default"}
        variant={g.source === "entra" ? "filled" : "outlined"}
        sx={{ fontSize: "0.65rem", flexShrink: 0 }}
      />
      <Chip
        label={`${g.member_count} member${g.member_count !== 1 ? "s" : ""}`}
        size="small"
        variant="outlined"
        sx={{ fontSize: "0.7rem", flexShrink: 0 }}
      />
      <Tooltip title="Manage members">
        <IconButton aria-label="Manage members" size="small" onClick={() => onMembers(g)} sx={{ color: "primary.main" }}>
          <ManageAccountsIcon sx={{ fontSize: 18 }} />
        </IconButton>
      </Tooltip>
      <Tooltip title="Delete this group">
        <IconButton aria-label="Delete this group" size="small" color="error" onClick={() => onDelete(g)}>
          <DeleteOutlineIcon sx={{ fontSize: 18 }} />
        </IconButton>
      </Tooltip>
    </Paper>
  );
}

export function GroupCreateDialog({
  open, name, desc, orgId, orgs, submitting, setName, setDesc, setOrgId, onClose, onSave,
}: {
  open: boolean;
  name: string;
  desc: string;
  orgId: string;
  orgs: { id: string; name: string }[];
  submitting: boolean;
  setName: (v: string) => void;
  setDesc: (v: string) => void;
  setOrgId: (v: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create a group</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          You can add people to the group after creating it.
        </Typography>
        <TextField fullWidth label="Group name" value={name} onChange={(e) => setName(e.target.value)}
          size="small" sx={{ mb: 2 }} />
        <TextField fullWidth label="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)}
          size="small" sx={{ mb: 2 }} />
        <FormControl fullWidth size="small">
          <InputLabel>Organisation (optional)</InputLabel>
          <Select value={orgId} label="Organisation (optional)" onChange={(e) => setOrgId(e.target.value)}>
            <MenuItem value="">None</MenuItem>
            {orgs.map((o) => <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>)}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={onSave} disabled={submitting || !name.trim()}>
          {submitting ? "Creating..." : "Create group"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
