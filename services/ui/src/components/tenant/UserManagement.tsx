"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import ManageAccountsIcon from "@mui/icons-material/ManageAccounts";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import InputAdornment from "@mui/material/InputAdornment";
import {
  assignUserRole, createGroup, createUser, deleteGroup, deleteUser,
  forceLogoutUser, listGroupMembers, listGroups, listOrgs, listRoles,
  listUsers, addGroupMember, removeGroupMember,
  type Group, type User,
} from "@/lib/api/admin";
import ConfirmDialog from "@/components/ConfirmDialog";

// -- Helpers --

function initials(nameOrEmail: string): string {
  const parts = nameOrEmail.split(/[\s@.]+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

function avatarColor(str: string): string {
  const palette = ["#1565c0", "#2e7d32", "#6a1b9a", "#c62828", "#e65100", "#00695c", "#37474f"];
  let h = 0;
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h);
  return palette[Math.abs(h) % palette.length];
}

function relativeTime(isoStr?: string | null): string {
  if (!isoStr) return "Never";
  const mins = Math.floor((Date.now() - new Date(isoStr).getTime()) / 60_000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function friendlyRole(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// -- Main component --

export default function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);
  const [roles, setRoles] = useState<{ name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteAdmin, setInviteAdmin] = useState(false);
  const [inviteOrgIds, setInviteOrgIds] = useState<string[]>([]);
  const [inviteRole, setInviteRole] = useState("");
  const [inviteSubmitting, setInviteSubmitting] = useState(false);

  const [groupAddOpen, setGroupAddOpen] = useState(false);
  const [groupAddName, setGroupAddName] = useState("");
  const [groupAddDesc, setGroupAddDesc] = useState("");
  const [groupAddOrgId, setGroupAddOrgId] = useState("");
  const [groupAddSubmitting, setGroupAddSubmitting] = useState(false);

  const [userSearch, setUserSearch] = useState("");

  const [logoutConfirm, setLogoutConfirm] = useState<User | null>(null);
  const [deactivateConfirm, setDeactivateConfirm] = useState<User | null>(null);
  const [groupDeleteConfirm, setGroupDeleteConfirm] = useState<Group | null>(null);
  const [memberDialog, setMemberDialog] = useState<Group | null>(null);
  const [memberAddEmail, setMemberAddEmail] = useState("");
  const [memberRefresh, setMemberRefresh] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, g, o, r] = await Promise.all([listUsers(), listGroups(), listOrgs(), listRoles()]);
      setUsers(u);
      setGroups(g);
      setOrgs(o.map((x) => ({ id: x.id, name: x.name })));
      setRoles(r.map((x) => ({ name: x.name })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load people and groups.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviteSubmitting(true);
    try {
      const email = inviteEmail.trim().toLowerCase();
      await createUser({ email, name: inviteName.trim() || email, is_platform_admin: inviteAdmin, org_ids: inviteOrgIds });
      if (inviteRole) await assignUserRole(email, { role_name: inviteRole });
      setInviteOpen(false);
      setInviteEmail(""); setInviteName(""); setInviteAdmin(false); setInviteOrgIds([]); setInviteRole("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add this person.");
    } finally {
      setInviteSubmitting(false);
    }
  };

  const handleForceLogout = async () => {
    if (!logoutConfirm) return;
    try { await forceLogoutUser(logoutConfirm.email); setLogoutConfirm(null); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not log this person out."); }
  };

  const handleDeactivate = async () => {
    if (!deactivateConfirm) return;
    try { await deleteUser(deactivateConfirm.email); setDeactivateConfirm(null); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not remove this person."); }
  };

  const handleCreateGroup = async () => {
    if (!groupAddName.trim()) return;
    setGroupAddSubmitting(true);
    try {
      await createGroup({ name: groupAddName.trim(), description: groupAddDesc.trim() || undefined, org_id: groupAddOrgId || undefined });
      setGroupAddOpen(false);
      setGroupAddName(""); setGroupAddDesc(""); setGroupAddOrgId("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the group.");
    } finally {
      setGroupAddSubmitting(false);
    }
  };

  const handleDeleteGroup = async () => {
    if (!groupDeleteConfirm) return;
    try { await deleteGroup(groupDeleteConfirm.id); setGroupDeleteConfirm(null); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not remove this group."); }
  };

  const handleAddMember = async () => {
    if (!memberDialog || !memberAddEmail.trim()) return;
    try {
      await addGroupMember(memberDialog.id, { email: memberAddEmail.trim().toLowerCase() });
      setMemberAddEmail("");
      setMemberRefresh((n) => n + 1);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add this person to the group.");
    }
  };

  const handleRemoveMember = async (email: string) => {
    if (!memberDialog) return;
    try {
      await removeGroupMember(memberDialog.id, email);
      setMemberRefresh((n) => n + 1);
      setMemberDialog(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove this person from the group.");
    }
  };

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      u.name?.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      u.org_names?.some((n) => n.toLowerCase().includes(q))
    );
  }, [users, userSearch]);

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
      )}
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}><CircularProgress aria-label="Loading" /></Box>
      ) : (
        <Grid container spacing={4}>

          {/* ---- PEOPLE ---- */}
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
              <Button startIcon={<PersonAddAlt1Icon />} variant="contained" size="small" onClick={() => setInviteOpen(true)}>
                Add person
              </Button>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Everyone who can log in to LEO. Platform admins can see and change everything.
            </Typography>

            {/* ---- SEARCH ---- */}
            {users.length > 0 && (
              <TextField
                size="small"
                fullWidth
                placeholder="Search by name, email or organisation…"
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
              <Table size="small" sx={{ tableLayout: "fixed", width: "100%" }}>
                <TableHead>
                  <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.73rem", color: "text.secondary", pb: 1, border: 0 } }}>
                    <TableCell sx={{ width: "45%" }}>Person</TableCell>
                    <TableCell sx={{ width: "28%" }}>Role</TableCell>
                    <TableCell sx={{ width: "20%" }}>Status</TableCell>
                    <TableCell sx={{ width: "7%" }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredUsers.map((u) => {
                    const roleNames = (u.roles || []).map((r) => r.role).filter(Boolean);
                    const isOnline = u.active_sessions_count > 0;
                    return (
                      <TableRow key={u.email} hover sx={{ "&:last-child td": { border: 0 } }}>
                        <TableCell sx={{ py: 1.25 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
                            <Avatar sx={{ width: 34, height: 34, fontSize: "0.78rem", bgcolor: avatarColor(u.email), flexShrink: 0 }}>
                              {initials(u.name || u.email)}
                            </Avatar>
                            <Box sx={{ minWidth: 0 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
                                  {u.name}
                                </Typography>
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
                                    {u.org_names.length === 1
                                      ? u.org_names[0]
                                      : `${u.org_names[0]} +${u.org_names.length - 1} more`}
                                  </Typography>
                                </Tooltip>
                              )}
                            </Box>
                          </Box>
                        </TableCell>
                        <TableCell sx={{ py: 1.25 }}>
                          {roleNames.length > 0 ? (
                            <Tooltip title={roleNames.map(friendlyRole).join(", ")} placement="top">
                              <Chip
                                label={friendlyRole(roleNames[0])}
                                size="small"
                                variant="outlined"
                                sx={{ fontSize: "0.68rem", maxWidth: "100%", cursor: "default" }}
                              />
                            </Tooltip>
                          ) : (
                            <Typography variant="caption" color="text.disabled">No role</Typography>
                          )}
                        </TableCell>
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
                        <TableCell align="right" sx={{ py: 1.25, whiteSpace: "nowrap", pr: 0.5 }}>
                          {isOnline && (
                            <Tooltip title="Sign out of all devices now">
                              <IconButton aria-label="Sign out of all devices" size="small" onClick={() => setLogoutConfirm(u)} sx={{ color: "text.secondary" }}>
                                <LogoutIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </Tooltip>
                          )}
                          <Tooltip title="Remove from LEO">
                            <IconButton aria-label="Remove from LEO" size="small" color="error" onClick={() => setDeactivateConfirm(u)}>
                              <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </Grid>

          {/* ---- GROUPS ---- */}
          <Grid size={{ xs: 12, lg: 5 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <GroupsOutlinedIcon color="action" fontSize="small" />
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Groups</Typography>
                <Chip label={groups.length} size="small" />
              </Box>
              <Button variant="outlined" size="small" onClick={() => setGroupAddOpen(true)}>
                + Create group
              </Button>
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
                  <Paper key={g.id} variant="outlined" sx={{ px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.5 }}>
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }} noWrap>
                        {g.name}
                      </Typography>
                      {g.org_name && (
                        <Typography variant="caption" color="text.secondary">{g.org_name}</Typography>
                      )}
                    </Box>
                    <Chip
                      label={`${g.member_count} member${g.member_count !== 1 ? "s" : ""}`}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: "0.7rem", flexShrink: 0 }}
                    />
                    <Tooltip title="Manage members">
                      <IconButton aria-label="Manage members" size="small" onClick={() => setMemberDialog(g)} sx={{ color: "primary.main" }}>
                        <ManageAccountsIcon sx={{ fontSize: 18 }} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete this group">
                      <IconButton aria-label="Delete this group" size="small" color="error" onClick={() => setGroupDeleteConfirm(g)}>
                        <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                      </IconButton>
                    </Tooltip>
                  </Paper>
                ))}
              </Stack>
            )}
          </Grid>
        </Grid>
      )}

      {/* ---- ADD PERSON DIALOG ---- */}
      <Dialog open={inviteOpen} onClose={() => setInviteOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add a person</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            They will be able to log in with this email. You can set their role and which organisations they can see.
          </Typography>
          <TextField fullWidth label="Email address" type="email"
            value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
            size="small" sx={{ mb: 2 }} />
          <TextField fullWidth label="Full name"
            value={inviteName} onChange={(e) => setInviteName(e.target.value)}
            size="small" sx={{ mb: 2 }} />
          <FormControlLabel
            control={<Switch checked={inviteAdmin} onChange={(e) => setInviteAdmin(e.target.checked)} />}
            label={
              <>Platform admin{" "}
                <Typography component="span" variant="caption" color="text.secondary">
                  — can see and change everything
                </Typography>
              </>
            }
            sx={{ mb: 1 }}
          />
          <Divider sx={{ my: 1.5 }} />
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Organisations they can see</InputLabel>
            <Select multiple value={inviteOrgIds} label="Organisations they can see"
              onChange={(e) => setInviteOrgIds(e.target.value as string[])}
              renderValue={(sel) => (sel as string[]).map((id) => orgs.find((o) => o.id === id)?.name ?? id).join(", ")}>
              {orgs.map((o) => <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl fullWidth size="small">
            <InputLabel>Role</InputLabel>
            <Select value={inviteRole} label="Role" onChange={(e) => setInviteRole(e.target.value)}>
              <MenuItem value="">No role</MenuItem>
              {roles.map((r) => <MenuItem key={r.name} value={r.name}>{friendlyRole(r.name)}</MenuItem>)}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInviteOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleInvite} disabled={inviteSubmitting || !inviteEmail.trim()}>
            {inviteSubmitting ? "Adding..." : "Add person"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ---- CREATE GROUP DIALOG ---- */}
      <Dialog open={groupAddOpen} onClose={() => setGroupAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create a group</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            You can add people to the group after creating it.
          </Typography>
          <TextField fullWidth label="Group name"
            value={groupAddName} onChange={(e) => setGroupAddName(e.target.value)}
            size="small" sx={{ mb: 2 }} />
          <TextField fullWidth label="Description (optional)"
            value={groupAddDesc} onChange={(e) => setGroupAddDesc(e.target.value)}
            size="small" sx={{ mb: 2 }} />
          <FormControl fullWidth size="small">
            <InputLabel>Organisation (optional)</InputLabel>
            <Select value={groupAddOrgId} label="Organisation (optional)"
              onChange={(e) => setGroupAddOrgId(e.target.value)}>
              <MenuItem value="">None</MenuItem>
              {orgs.map((o) => <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>)}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGroupAddOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateGroup} disabled={groupAddSubmitting || !groupAddName.trim()}>
            {groupAddSubmitting ? "Creating..." : "Create group"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ---- MEMBER DIALOG ---- */}
      {memberDialog && (
        <MemberDialog
          group={memberDialog}
          refreshTrigger={memberRefresh}
          addEmail={memberAddEmail}
          setAddEmail={setMemberAddEmail}
          onAdd={handleAddMember}
          onRemove={handleRemoveMember}
          onClose={() => setMemberDialog(null)}
          loadMembers={() => listGroupMembers(memberDialog.id)}
        />
      )}

      {/* ---- CONFIRMATIONS ---- */}
      {logoutConfirm && (
        <ConfirmDialog
          title="Sign this person out"
          body={`This will sign "${logoutConfirm.name || logoutConfirm.email}" out of all devices right now. They can log back in.`}
          confirmLabel="Sign them out"
          variant="danger"
          onConfirm={handleForceLogout}
          onCancel={() => setLogoutConfirm(null)}
        />
      )}
      {deactivateConfirm && (
        <ConfirmDialog
          title="Remove this person"
          body={`Remove "${deactivateConfirm.name || deactivateConfirm.email}" from LEO? They will not be able to log in any more. Their history is kept.`}
          confirmLabel="Yes, remove them"
          variant="danger"
          onConfirm={handleDeactivate}
          onCancel={() => setDeactivateConfirm(null)}
        />
      )}
      {groupDeleteConfirm && (
        <ConfirmDialog
          title="Delete this group"
          body={`Delete "${groupDeleteConfirm.name}"? People in the group will not be deleted — they just leave this group.`}
          confirmLabel="Yes, delete it"
          variant="danger"
          onConfirm={handleDeleteGroup}
          onCancel={() => setGroupDeleteConfirm(null)}
        />
      )}
    </Box>
  );
}

// -- Member dialog (sub-component) --

function MemberDialog({
  group, refreshTrigger, addEmail, setAddEmail, onAdd, onRemove, onClose, loadMembers,
}: {
  group: Group;
  refreshTrigger?: number;
  addEmail: string;
  setAddEmail: (v: string) => void;
  onAdd: () => void;
  onRemove: (email: string) => void;
  onClose: () => void;
  loadMembers: () => Promise<Array<{ email: string; name?: string }>>;
}) {
  const [members, setMembers] = useState<Array<{ email: string; name?: string }>>([]);
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
            size="small" placeholder="Email address" fullWidth
            value={addEmail} onChange={(e) => setAddEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAdd()}
          />
          <Button variant="contained" size="small" onClick={onAdd} disabled={!addEmail.trim()}>Add</Button>
        </Box>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}><CircularProgress aria-label="Loading" size={24} /></Box>
        ) : members.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
            No members yet. Add someone above.
          </Typography>
        ) : (
          <Stack spacing={0.5}>
            {members.map((m) => (
              <Box key={m.email} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
                <Avatar sx={{ width: 28, height: 28, fontSize: "0.7rem", bgcolor: avatarColor(m.email) }}>
                  {initials(m.name || m.email)}
                </Avatar>
                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>{m.name || m.email}</Typography>
                  {m.name && <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>{m.email}</Typography>}
                </Box>
                <Tooltip title="Remove from group">
                  <IconButton aria-label="Remove from group" size="small" color="error" onClick={() => onRemove(m.email)}>
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
