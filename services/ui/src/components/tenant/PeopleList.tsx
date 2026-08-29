/**
 * People table for Platform Management.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 */
"use client";

import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import { type User } from "@/lib/api/admin";
import { avatarColor, initials, relativeTime } from "./userManagementHelpers";

interface Props {
  users: User[];
  filteredUsers: User[];
  userSearch: string;
  setUserSearch: (v: string) => void;
  onInvite: () => void;
  onEdit: (u: User) => void;
  onLogout: (u: User) => void;
  onDeactivate: (u: User) => void;
}

export default function PeopleList({
  users,
  filteredUsers,
  userSearch,
  setUserSearch,
  onInvite,
  onEdit,
  onLogout,
  onDeactivate,
}: Props) {
  return (
    <Grid size={{ xs: 12, lg: 7 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <PeopleAltOutlinedIcon color="action" fontSize="small" />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>People</Typography>
          <Chip
            label={filteredUsers.length < users.length ? `${filteredUsers.length} of ${users.length}` : users.length}
            size="small"
          />
        </Box>
        <Button startIcon={<PersonAddAlt1Icon />} variant="contained" size="small" onClick={onInvite}>
          Add person
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Everyone who can log in to LEO. Platform admins can see and change everything.
      </Typography>
      {users.length > 0 && (
        <TextField
          size="small"
          fullWidth
          placeholder="Search by name, email or organisation..."
          value={userSearch}
          onChange={(e) => setUserSearch(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchOutlinedIcon sx={{ fontSize: 16, color: "text.disabled" }} />
                </InputAdornment>
              ),
            },
          }}
          sx={{ mb: 2 }}
        />
      )}
      {users.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No people yet. Use &ldquo;Add person&rdquo; to get started.
        </Typography>
      ) : filteredUsers.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No people match your search.
        </Typography>
      ) : (
        <PeopleTable
          users={filteredUsers}
          onEdit={onEdit}
          onLogout={onLogout}
          onDeactivate={onDeactivate}
        />
      )}
    </Grid>
  );
}

function PeopleTable({
  users, onEdit, onLogout, onDeactivate,
}: {
  users: User[];
  onEdit: (u: User) => void;
  onLogout: (u: User) => void;
  onDeactivate: (u: User) => void;
}) {
  return (
    <Table size="small" sx={{ tableLayout: "fixed", width: "100%" }}>
      <TableHead>
        <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.73rem", color: "text.secondary", pb: 1, border: 0 } }}>
          <TableCell sx={{ width: "42%" }}>Person</TableCell>
          <TableCell sx={{ width: "28%" }}>Groups</TableCell>
          <TableCell sx={{ width: "18%" }}>Status</TableCell>
          <TableCell sx={{ width: "12%" }} />
        </TableRow>
      </TableHead>
      <TableBody>
        {users.map((u) => (
          <PersonRow
            key={u.email}
            user={u}
            onEdit={onEdit}
            onLogout={onLogout}
            onDeactivate={onDeactivate}
          />
        ))}
      </TableBody>
    </Table>
  );
}

function PersonRow({
  user: u, onEdit, onLogout, onDeactivate,
}: {
  user: User;
  onEdit: (u: User) => void;
  onLogout: (u: User) => void;
  onDeactivate: (u: User) => void;
}) {
  const isOnline = u.active_sessions_count > 0;
  const groupNames = (u.groups || []).map((g) => g.name).filter(Boolean);
  const hasLegacy = (u.legacy_roles || []).length > 0;
  return (
    <TableRow hover sx={{ "&:last-child td": { border: 0 } }}>
      <PersonCell user={u} />
      <TableCell sx={{ py: 1.25 }}>
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
          {groupNames.length > 0 ? (
            <Chip label={groupNames[0]} size="small" variant="outlined" sx={{ fontSize: "0.68rem" }} />
          ) : (
            <Typography variant="caption" color="text.disabled">No groups</Typography>
          )}
          {hasLegacy && (
            <Chip label="Old role schema" size="small" color="warning" sx={{ height: 18, fontSize: "0.6rem" }} />
          )}
        </Stack>
      </TableCell>
      <StatusCell user={u} isOnline={isOnline} />
      <TableCell align="right" sx={{ py: 1.25, whiteSpace: "nowrap", pr: 0.5 }}>
        <Tooltip title="Edit person">
          <IconButton
            aria-label="Edit person"
            data-testid="people-edit"
            size="small"
            onClick={() => onEdit(u)}
            sx={{ color: "text.secondary" }}
          >
            <EditOutlinedIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
        {isOnline && (
          <Tooltip title="Sign out of all devices now">
            <IconButton aria-label="Sign out of all devices" size="small" onClick={() => onLogout(u)} sx={{ color: "text.secondary" }}>
              <LogoutIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Remove from LEO">
          <IconButton aria-label="Remove from LEO" size="small" color="error" onClick={() => onDeactivate(u)}>
            <DeleteOutlineIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

function PersonCell({ user: u }: { user: User }) {
  return (
    <TableCell sx={{ py: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
        <Avatar sx={{ width: 34, height: 34, fontSize: "0.78rem", bgcolor: avatarColor(u.email), flexShrink: 0 }}>
          {initials(u.name || u.email)}
        </Avatar>
        <Box sx={{ minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
            <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>{u.name}</Typography>
            {u.is_platform_admin && (
              <Chip label="Admin" size="small" color="primary"
                sx={{ height: 16, fontSize: "0.6rem", "& .MuiChip-label": { px: 0.75 } }} />
            )}
          </Box>
          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
            {u.email}
          </Typography>
          {!u.is_platform_admin && u.org_names && u.org_names.length > 0 && (
            <Tooltip title={u.org_names.join(", ")} placement="top" disableHoverListener={u.org_names.length <= 1}>
              <Typography variant="caption" color="text.disabled" noWrap sx={{ display: "block", fontSize: "0.65rem" }}>
                {u.org_names.length === 1 ? u.org_names[0] : `${u.org_names[0]} +${u.org_names.length - 1} more`}
              </Typography>
            </Tooltip>
          )}
        </Box>
      </Box>
    </TableCell>
  );
}

function StatusCell({ user: u, isOnline }: { user: User; isOnline: boolean }) {
  return (
    <TableCell sx={{ py: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Box sx={{
          width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
          bgcolor: isOnline ? "success.main" : "grey.400",
        }} />
        <Typography variant="caption" color="text.secondary" noWrap>
          {isOnline
            ? `${u.active_sessions_count} device${u.active_sessions_count !== 1 ? "s" : ""}`
            : relativeTime(u.last_seen_at)}
        </Typography>
      </Box>
    </TableCell>
  );
}
