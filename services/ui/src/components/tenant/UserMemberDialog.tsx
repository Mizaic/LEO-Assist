/**
 * Manage who is in a group.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 */
"use client";

import { useEffect, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { type Group } from "@/lib/api/admin";
import { avatarColor, initials } from "./userManagementHelpers";

interface Props {
  group: Group;
  refreshTrigger?: number;
  addEmail: string;
  setAddEmail: (v: string) => void;
  onAdd: () => void;
  onRemove: (email: string) => void;
  onClose: () => void;
  loadMembers: () => Promise<Array<{ email: string; name?: string }>>;
}

export default function UserMemberDialog({
  group,
  refreshTrigger,
  addEmail,
  setAddEmail,
  onAdd,
  onRemove,
  onClose,
  loadMembers,
}: Props) {
  const [members, setMembers] = useState<Array<{ email: string; name?: string }>>(
    []
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    loadMembers().then(setMembers).finally(() => setLoading(false));
  }, [group.id, refreshTrigger, loadMembers]);

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        {group.name}
        <Typography variant="body2" color="text.secondary">
          {group.member_count} member{group.member_count !== 1 ? "s" : ""}
        </Typography>
      </DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
          <TextField
            size="small"
            placeholder="Email address"
            fullWidth
            value={addEmail}
            onChange={(e) => setAddEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAdd()}
          />
          <Button
            variant="contained"
            size="small"
            onClick={onAdd}
            disabled={!addEmail.trim()}
          >
            Add
          </Button>
        </Box>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <CircularProgress aria-label="Loading" size={24} />
          </Box>
        ) : members.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
            No members yet. Add someone above.
          </Typography>
        ) : (
          <Stack spacing={0.5}>
            {members.map((m) => (
              <Box key={m.email} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
                <Avatar
                  sx={{
                    width: 28,
                    height: 28,
                    fontSize: "0.7rem",
                    bgcolor: avatarColor(m.email),
                  }}
                >
                  {initials(m.name || m.email)}
                </Avatar>
                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
                    {m.name || m.email}
                  </Typography>
                  {m.name && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      noWrap
                      sx={{ display: "block" }}
                    >
                      {m.email}
                    </Typography>
                  )}
                </Box>
                <Tooltip title="Remove from group">
                  <IconButton
                    aria-label="Remove from group"
                    size="small"
                    color="error"
                    onClick={() => onRemove(m.email)}
                  >
                    <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
              </Box>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
