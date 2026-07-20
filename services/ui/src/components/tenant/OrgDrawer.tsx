/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BusinessIcon from "@mui/icons-material/Business";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HubIcon from "@mui/icons-material/Hub";
import LinkOffIcon from "@mui/icons-material/LinkOff";
import LocalHospitalIcon from "@mui/icons-material/LocalHospital";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import Avatar from "@mui/material/Avatar";
import Collapse from "@mui/material/Collapse";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemAvatar from "@mui/material/ListItemAvatar";
import ListItemText from "@mui/material/ListItemText";
import {
  acquireGpToPcn,
  addUserToOrg,
  assignOrgRole,
  deleteOrg,
  listOrgs,
  listOrgServices,
  listOrgUsers,
  patchOrg,
  releaseGpFromPcn,
  removeOrgRole,
  removeUserFromOrg,
  type Org,
  type OrgService,
  type User,
} from "@/lib/api/admin";
import ConfirmDialog from "@/components/ConfirmDialog";

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

const ORG_TYPE_CONFIG: Record<
  string,
  { label: string; color: "success" | "info" | "secondary" | "default" | "warning" }
> = {
  gp: { label: "GP Practice", color: "success" },
  pcn: { label: "PCN", color: "warning" },
  icb: { label: "ICB", color: "info" },
  alliance: { label: "Cancer Alliance", color: "secondary" },
  service_provider: { label: "Service Provider", color: "info" },
  organization: { label: "Organisation", color: "default" },
};

function SyncStatusBadge({ status }: { status?: string }) {
  if (!status || status === "ok") {
    return (
      <Chip
        icon={<CheckCircleOutlineIcon />}
        label="In sync"
        color="success"
        size="small"
        variant="outlined"
      />
    );
  }
  if (status === "mismatch") {
    return (
      <Chip
        icon={<WarningAmberIcon />}
        label="Mismatch"
        color="warning"
        size="small"
      />
    );
  }
  if (status === "closed") {
    return (
      <Chip
        icon={<ErrorOutlineIcon />}
        label="ODS Inactive"
        color="error"
        size="small"
      />
    );
  }
  if (status === "error") {
    return <Chip label="Sync error" color="default" size="small" />;
  }
  return <Chip label={status} size="small" variant="outlined" />;
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", py: 0.75 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130 }}>
        {label}
      </Typography>
      <Box sx={{ textAlign: "right" }}>{value}</Box>
    </Box>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ display: "block", fontSize: "0.68rem", letterSpacing: 1, mt: 2.5, mb: 0.5 }}
    >
      {children}
    </Typography>
  );
}

// ------------------------------------------------------------------
// Props
// ------------------------------------------------------------------

interface OrgDrawerProps {
  org: Org | null;
  onClose: () => void;
  onChanged: () => void;
}

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export default function OrgDrawer({ org, onClose, onChanged }: OrgDrawerProps) {
  const [pcns, setPcns] = useState<Org[]>([]);
  const [loadingPcns, setLoadingPcns] = useState(false);
  const [spServices, setSpServices] = useState<OrgService[]>([]);
  const [loadingSpServices, setLoadingSpServices] = useState(false);

  // People
  const [orgUsers, setOrgUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [addUserEmail, setAddUserEmail] = useState("");
  const [addUserBusy, setAddUserBusy] = useState(false);
  const [showAddUser, setShowAddUser] = useState(false);
  const [roleAssigning, setRoleAssigning] = useState<string | null>(null); // email of user being role-changed
  const [userToRemove, setUserToRemove] = useState<User | null>(null);

  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");
  const [editShortName, setEditShortName] = useState("");
  const [editOds, setEditOds] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  const [pcnAction, setPcnAction] = useState<"acquire" | "release" | null>(null);
  const [selectedPcnId, setSelectedPcnId] = useState("");
  const [pcnBusy, setPcnBusy] = useState(false);

  const [deleteConfirm, setDeleteConfirm] = useState(false);

  const [actionError, setActionError] = useState<string | null>(null);

  const loadOrgUsers = useCallback((orgId: string) => {
    setLoadingUsers(true);
    listOrgUsers(orgId)
      .then(setOrgUsers)
      .catch(() => setOrgUsers([]))
      .finally(() => setLoadingUsers(false));
  }, []);

  // Fetch PCN list when a GP practice drawer is opened
  useEffect(() => {
    if (!org || org.type !== "gp") {
      setPcns([]);
      return;
    }
    setLoadingPcns(true);
    listOrgs()
      .then((all) => setPcns(all.filter((o) => o.type === "pcn")))
      .catch(() => setPcns([]))
      .finally(() => setLoadingPcns(false));
  }, [org?.id, org?.type]);

  // Fetch linked services when a Service Provider drawer is opened
  useEffect(() => {
    if (!org || org.type !== "service_provider") {
      setSpServices([]);
      return;
    }
    setLoadingSpServices(true);
    listOrgServices(org.id)
      .then(setSpServices)
      .catch(() => setSpServices([]))
      .finally(() => setLoadingSpServices(false));
  }, [org?.id, org?.type]);

  // Fetch users whenever the drawer opens for an org
  useEffect(() => {
    if (org) loadOrgUsers(org.id);
    else setOrgUsers([]);
  }, [org?.id, loadOrgUsers]);

  // Initialise edit form when org changes
  useEffect(() => {
    if (org) {
      setEditName(org.name);
      setEditShortName(org.short_name ?? "");
      setEditOds(org.odsCode ?? "");
      setEditMode(false);
      setPcnAction(null);
      setSelectedPcnId("");
      setActionError(null);
      setAddUserEmail("");
      setShowAddUser(false);
      setUserToRemove(null);
    }
  }, [org?.id]);

  if (!org) return null;

  const tc = ORG_TYPE_CONFIG[org.type] ?? ORG_TYPE_CONFIG.organization;
  const discrepancy = org.ods_discrepancy ?? {};
  const hasMismatch = Object.keys(discrepancy).length > 0;
  const currentPcnId = org.pcn_id ?? null;
  const currentPcnName = org.pcn_name ?? null;

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------

  const handleSaveEdit = async () => {
    setEditSaving(true);
    setActionError(null);
    try {
      await patchOrg(org.id, {
        name: editName.trim() || undefined,
        short_name: editShortName.trim() || undefined,
        ods_code: editOds.trim() || undefined,
      });
      setEditMode(false);
      onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not save changes.");
    } finally {
      setEditSaving(false);
    }
  };

  const handlePcnAction = async () => {
    if (!selectedPcnId) return;
    setPcnBusy(true);
    setActionError(null);
    try {
      if (pcnAction === "acquire") {
        await acquireGpToPcn(org.id, selectedPcnId);
      } else {
        await releaseGpFromPcn(org.id, selectedPcnId);
      }
      setPcnAction(null);
      setSelectedPcnId("");
      onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "PCN action failed.");
    } finally {
      setPcnBusy(false);
    }
  };

  const handleAddUser = async () => {
    if (!org || !addUserEmail.trim()) return;
    setAddUserBusy(true);
    setActionError(null);
    try {
      await addUserToOrg(org.id, addUserEmail.trim().toLowerCase());
      setAddUserEmail("");
      setShowAddUser(false);
      loadOrgUsers(org.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not add user to organisation.");
    } finally {
      setAddUserBusy(false);
    }
  };

  const handleRemoveUser = async (user: User) => {
    if (!org) return;
    setActionError(null);
    try {
      await removeUserFromOrg(org.id, user.email);
      setUserToRemove(null);
      loadOrgUsers(org.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not remove user.");
      setUserToRemove(null);
    }
  };

  const handleAssignRole = async (user: User, roleName: string) => {
    if (!org) return;
    setRoleAssigning(user.email);
    setActionError(null);
    try {
      // Remove existing org-scoped role for this org first
      const existing = user.roles.find((r) => r.org_id === org.id);
      if (existing) await removeOrgRole(user.email, existing.role);
      if (roleName) await assignOrgRole(user.email, org.id, roleName);
      loadOrgUsers(org.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not update role.");
    } finally {
      setRoleAssigning(null);
    }
  };

  const handleDelete = async () => {
    setActionError(null);
    try {
      await deleteOrg(org.id);
      setDeleteConfirm(false);
      onClose();
      onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not remove organisation.");
      setDeleteConfirm(false);
    }
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <>
      <Drawer
        anchor="right"
        open={!!org}
        onClose={onClose}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 0 } }}
      >
        {/* ---- Header ---- */}
        <Box
          sx={{
            px: 3,
            pt: 3,
            pb: 2,
            borderBottom: "1px solid",
            borderColor: "divider",
            background: (t) =>
              t.palette.mode === "dark" ? t.palette.grey[900] : t.palette.grey[50],
          }}
        >
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
              {org.type === "gp" ? (
                <LocalHospitalIcon color="success" />
              ) : org.type === "pcn" ? (
                <HubIcon color="warning" />
              ) : (
                <BusinessIcon color="primary" />
              )}
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                  {org.name}
                </Typography>
                {org.short_name && (
                  <Typography variant="caption" color="text.secondary">
                    {org.short_name}
                  </Typography>
                )}
              </Box>
            </Box>
            <IconButton onClick={onClose} size="small" aria-label="Close">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
          <Box sx={{ display: "flex", gap: 1, mt: 1.5, flexWrap: "wrap" }}>
            <Chip label={tc.label} color={tc.color} size="small" />
            {org.odsCode && (
              <Chip
                label={org.odsCode}
                size="small"
                variant="outlined"
                sx={{ fontFamily: "monospace" }}
              />
            )}
            {org.onboarding_status === "pending" && (
              <Chip label="Pending setup" color="warning" size="small" variant="outlined" />
            )}
            {org.onboarding_status === "complete" && (
              <Chip label="Active" color="success" size="small" variant="outlined" />
            )}
          </Box>
        </Box>

        {/* ---- Body ---- */}
        <Box sx={{ px: 3, py: 2, overflowY: "auto", flex: 1 }}>

          {actionError && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
              {actionError}
            </Alert>
          )}

          {/* ---- Organisation details ---- */}
          <SectionTitle>Organisation details</SectionTitle>
          <Divider />

          {!editMode ? (
            <Box sx={{ mt: 0.5 }}>
              <DetailRow
                label="Patients"
                value={
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {org.patient_count > 0 ? org.patient_count.toLocaleString() : (
                      <Typography component="span" variant="caption" color="text.disabled">None</Typography>
                    )}
                  </Typography>
                }
              />
              <DetailRow
                label="Part of"
                value={
                  <Typography variant="body2">
                    {org.parent_name || org.alliance_name || (
                      <Typography component="span" variant="caption" color="text.disabled">—</Typography>
                    )}
                  </Typography>
                }
              />
              {currentPcnId && org.type === "gp" && (
                <DetailRow
                  label="PCN"
                  value={<Typography variant="body2">{currentPcnName ?? currentPcnId}</Typography>}
                />
              )}
              {org.entra_tenant_id && (
                <DetailRow
                  label="Entra tenant"
                  value={
                    <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}>
                      {org.entra_tenant_id}
                    </Typography>
                  }
                />
              )}
              <Box sx={{ mt: 1 }}>
                <Button
                  size="small"
                  startIcon={<EditIcon />}
                  onClick={() => setEditMode(true)}
                  variant="outlined"
                >
                  Edit details
                </Button>
              </Box>
            </Box>
          ) : (
            <Stack spacing={2} sx={{ mt: 1.5 }}>
              <TextField
                label="Name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                size="small"
                fullWidth
              />
              <TextField
                label="Short name (optional)"
                value={editShortName}
                onChange={(e) => setEditShortName(e.target.value)}
                size="small"
                fullWidth
              />
              <TextField
                label="ODS code (optional)"
                value={editOds}
                onChange={(e) => setEditOds(e.target.value)}
                size="small"
                fullWidth
                helperText="Changing this triggers re-validation against the NHS ODS API on the next sync."
              />
              <Box sx={{ display: "flex", gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  onClick={handleSaveEdit}
                  disabled={editSaving || !editName.trim()}
                >
                  {editSaving ? "Saving…" : "Save"}
                </Button>
                <Button size="small" onClick={() => setEditMode(false)} disabled={editSaving}>
                  Cancel
                </Button>
              </Box>
            </Stack>
          )}

          {/* ---- ODS Sync ---- */}
          <SectionTitle>ODS sync</SectionTitle>
          <Divider />
          <Box sx={{ mt: 0.5 }}>
            <DetailRow
              label="Status"
              value={<SyncStatusBadge status={org.ods_sync_status} />}
            />
            {org.ods_sync_last_checked && (
              <DetailRow
                label="Last checked"
                value={
                  <Typography variant="caption" color="text.secondary">
                    {new Date(org.ods_sync_last_checked).toLocaleString("en-GB")}
                  </Typography>
                }
              />
            )}
            {hasMismatch && (
              <Box
                sx={{
                  mt: 1,
                  p: 1.5,
                  borderRadius: 1,
                  bgcolor: "warning.light",
                  border: "1px solid",
                  borderColor: "warning.main",
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 700, color: "warning.dark", display: "block", mb: 0.5 }}>
                  Discrepancies found
                </Typography>
                {Object.entries(discrepancy).map(([field, diff]) => (
                  <Box key={field} sx={{ mb: 0.5 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, textTransform: "capitalize" }}>
                      {field}
                    </Typography>
                    <Box sx={{ display: "flex", gap: 2, ml: 1 }}>
                      <Typography variant="caption" color="text.secondary">
                        LEO: <strong>{(diff as { leo: string }).leo}</strong>
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        ODS: <strong>{(diff as { ods: string }).ods}</strong>
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            )}
          </Box>

          {/* ---- Linked services (Service Provider only) ---- */}
          {org.type === "service_provider" && (
            <>
              <SectionTitle>Linked services</SectionTitle>
              <Divider />
              <Box sx={{ mt: 0.5 }}>
                {loadingSpServices ? (
                  <CircularProgress size={16} aria-label="Loading services" />
                ) : spServices.length === 0 ? (
                  <Typography variant="caption" color="text.disabled">
                    No services linked to this organisation yet.
                  </Typography>
                ) : (
                  <List dense disablePadding>
                    {spServices.map((svc) => (
                      <ListItem key={svc.id} disableGutters sx={{ py: 0.25 }}>
                        <ListItemAvatar sx={{ minWidth: 36 }}>
                          <Avatar sx={{ width: 28, height: 28, bgcolor: "info.light" }}>
                            <LocalHospitalIcon sx={{ fontSize: 16 }} />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={svc.name || svc.id}
                          secondary={svc.code || svc.id}
                          primaryTypographyProps={{ variant: "body2", fontWeight: 500 }}
                          secondaryTypographyProps={{ variant: "caption" }}
                        />
                      </ListItem>
                    ))}
                  </List>
                )}
              </Box>
            </>
          )}

          {/* ---- PCN membership (GP only) ---- */}
          {org.type === "gp" && (
            <>
              <SectionTitle>PCN membership</SectionTitle>
              <Divider />
              <Box sx={{ mt: 0.5 }}>
                {loadingPcns ? (
                  <CircularProgress size={16} />
                ) : currentPcnId ? (
                  <>
                    <DetailRow
                      label="Current PCN"
                      value={<Typography variant="body2" sx={{ fontWeight: 500 }}>{currentPcnName ?? currentPcnId}</Typography>}
                    />
                    {pcnAction === "release" ? (
                      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                        <FormControl size="small" sx={{ minWidth: 220 }}>
                          <InputLabel>PCN to release from</InputLabel>
                          <Select
                            value={selectedPcnId}
                            label="PCN to release from"
                            onChange={(e) => setSelectedPcnId(e.target.value)}
                          >
                            <MenuItem value={currentPcnId}>{currentPcnName ?? currentPcnId}</MenuItem>
                          </Select>
                        </FormControl>
                        <Button
                          variant="contained"
                          color="warning"
                          size="small"
                          startIcon={<LinkOffIcon />}
                          onClick={handlePcnAction}
                          disabled={pcnBusy || !selectedPcnId}
                        >
                          {pcnBusy ? "Releasing…" : "Confirm release"}
                        </Button>
                        <Button size="small" onClick={() => setPcnAction(null)} disabled={pcnBusy}>Cancel</Button>
                      </Stack>
                    ) : (
                      <Button
                        size="small"
                        color="warning"
                        startIcon={<LinkOffIcon />}
                        sx={{ mt: 0.5 }}
                        onClick={() => { setPcnAction("release"); setSelectedPcnId(currentPcnId); }}
                      >
                        Release from PCN
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 1 }}>
                      This practice is not currently in a PCN.
                    </Typography>
                    {pcnAction === "acquire" ? (
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        <FormControl size="small" sx={{ minWidth: 220 }}>
                          <InputLabel>Select PCN</InputLabel>
                          <Select
                            value={selectedPcnId}
                            label="Select PCN"
                            onChange={(e) => setSelectedPcnId(e.target.value)}
                          >
                            {pcns.map((p) => (
                              <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        <Button
                          variant="contained"
                          size="small"
                          startIcon={<HubIcon />}
                          onClick={handlePcnAction}
                          disabled={pcnBusy || !selectedPcnId}
                        >
                          {pcnBusy ? "Adding…" : "Acquire"}
                        </Button>
                        <Button size="small" onClick={() => setPcnAction(null)} disabled={pcnBusy}>Cancel</Button>
                      </Stack>
                    ) : (
                      <Button
                        size="small"
                        startIcon={<HubIcon />}
                        onClick={() => setPcnAction("acquire")}
                      >
                        Add to a PCN
                      </Button>
                    )}
                  </>
                )}
              </Box>
            </>
          )}

          {/* ---- Subscription ---- */}
          {org.subscription && (
            <>
              <SectionTitle>Subscription</SectionTitle>
              <Divider />
              <Box sx={{ mt: 0.5 }}>
                <DetailRow
                  label="Tier"
                  value={<Chip label={org.subscription.tier} size="small" variant="outlined" />}
                />
                <DetailRow
                  label="Credits remaining"
                  value={
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {(org.subscription.credits_purchased - org.subscription.credits_consumed).toLocaleString()}
                      <Typography component="span" variant="caption" color="text.secondary">
                        {" "}/ {org.subscription.credits_purchased.toLocaleString()}
                      </Typography>
                    </Typography>
                  }
                />
                {org.subscription.expires_at && (
                  <DetailRow
                    label="Expires"
                    value={
                      <Typography variant="caption" color="text.secondary">
                        {new Date(org.subscription.expires_at).toLocaleDateString("en-GB")}
                      </Typography>
                    }
                  />
                )}
              </Box>
            </>
          )}

          {/* ---- People ---- */}
          <SectionTitle>People</SectionTitle>
          <Divider />
          <Box sx={{ mt: 0.5 }}>
            {loadingUsers ? (
              <Box sx={{ py: 1 }}><CircularProgress size={16} /></Box>
            ) : orgUsers.length === 0 ? (
              <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 1 }}>
                No users associated with this organisation.
              </Typography>
            ) : (
              <List dense disablePadding>
                {orgUsers.map((u) => {
                  const orgRole = u.roles.find((r) => r.org_id === org.id || r.org_id === "" || !r.org_id);
                  const initials = (u.name || u.email)
                    .split(/\s+/)
                    .map((w) => w[0])
                    .slice(0, 2)
                    .join("")
                    .toUpperCase();
                  const lastSeen = u.last_seen_at
                    ? new Date(u.last_seen_at).toLocaleDateString("en-GB")
                    : null;
                  return (
                    <ListItem
                      key={u.email}
                      disableGutters
                      sx={{
                        py: 0.75,
                        borderBottom: "1px solid",
                        borderColor: "divider",
                        alignItems: "flex-start",
                      }}
                      secondaryAction={
                        <Tooltip title="Remove from this organisation">
                          <IconButton
                            edge="end"
                            size="small"
                            color="error"
                            onClick={() => setUserToRemove(u)}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      }
                    >
                      <ListItemAvatar sx={{ minWidth: 40, mt: 0.5 }}>
                        <Avatar sx={{ width: 30, height: 30, fontSize: "0.7rem", bgcolor: "primary.main" }}>
                          {initials}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                              {u.name || u.email}
                            </Typography>
                            {u.active_sessions_count > 0 && (
                              <Tooltip title="Currently active">
                                <Box
                                  component="span"
                                  sx={{
                                    width: 7,
                                    height: 7,
                                    borderRadius: "50%",
                                    bgcolor: "success.main",
                                    display: "inline-block",
                                  }}
                                />
                              </Tooltip>
                            )}
                          </Box>
                        }
                        secondary={
                          <Box component="span" sx={{ display: "flex", flexDirection: "column", gap: 0.5, mt: 0.25 }}>
                            <Typography variant="caption" color="text.secondary">{u.email}</Typography>
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                              <FormControl size="small" variant="standard" sx={{ minWidth: 130 }}>
                                <Select
                                  value={orgRole?.role ?? ""}
                                  displayEmpty
                                  disabled={roleAssigning === u.email}
                                  onChange={(e) => handleAssignRole(u, e.target.value)}
                                  sx={{ fontSize: "0.75rem" }}
                                  renderValue={(v) =>
                                    v ? (
                                      <Chip label={v.replace(/_/g, " ")} size="small" sx={{ height: 18, fontSize: "0.68rem" }} />
                                    ) : (
                                      <Typography variant="caption" color="text.disabled">No role</Typography>
                                    )
                                  }
                                >
                                  <MenuItem value=""><em>No role</em></MenuItem>
                                  <MenuItem value="org_admin">Org admin</MenuItem>
                                  <MenuItem value="clinical_coder">Clinical coder</MenuItem>
                                  <MenuItem value="clinical_viewer">Clinical viewer</MenuItem>
                                  <MenuItem value="read_only">Read only</MenuItem>
                                  <MenuItem value="auditor">Auditor</MenuItem>
                                </Select>
                              </FormControl>
                              {lastSeen && (
                                <Typography variant="caption" color="text.disabled" sx={{ ml: 0.5 }}>
                                  · last seen {lastSeen}
                                </Typography>
                              )}
                            </Box>
                          </Box>
                        }
                        disableTypography
                      />
                    </ListItem>
                  );
                })}
              </List>
            )}

            {/* Add user inline */}
            <Collapse in={showAddUser} timeout="auto">
              <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: "center" }}>
                <TextField
                  size="small"
                  label="User email"
                  placeholder="name@nhs.net"
                  value={addUserEmail}
                  onChange={(e) => setAddUserEmail(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleAddUser(); }}
                  sx={{ flex: 1 }}
                  helperText="The user must already exist in the system."
                />
                <Button
                  variant="contained"
                  size="small"
                  onClick={handleAddUser}
                  disabled={addUserBusy || !addUserEmail.trim()}
                  sx={{ mt: -2 }}
                >
                  {addUserBusy ? "Adding…" : "Add"}
                </Button>
                <Button
                  size="small"
                  onClick={() => { setShowAddUser(false); setAddUserEmail(""); }}
                  disabled={addUserBusy}
                  sx={{ mt: -2 }}
                >
                  Cancel
                </Button>
              </Stack>
            </Collapse>

            {!showAddUser && (
              <Button
                size="small"
                startIcon={<PersonAddIcon />}
                sx={{ mt: 1 }}
                onClick={() => setShowAddUser(true)}
              >
                Associate user
              </Button>
            )}
          </Box>

          {/* ---- Danger zone ---- */}
          <SectionTitle>Actions</SectionTitle>
          <Divider />
          <Box sx={{ mt: 1 }}>
            <Tooltip
              title={
                org.patient_count > 0
                  ? "Cannot remove: this organisation has patients linked to it."
                  : "Permanently remove this organisation."
              }
            >
              <span>
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  onClick={() => setDeleteConfirm(true)}
                  disabled={org.patient_count > 0}
                >
                  Remove organisation
                </Button>
              </span>
            </Tooltip>
          </Box>
        </Box>

        {/* ---- Footer ---- */}
        <Box
          sx={{
            px: 3,
            py: 1.5,
            borderTop: "1px solid",
            borderColor: "divider",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <Button onClick={onClose} size="small">
            Close
          </Button>
        </Box>
      </Drawer>

      {deleteConfirm && (
        <ConfirmDialog
          title="Remove organisation"
          body={`Remove "${org.name}" from the system? This cannot be undone.`}
          confirmLabel="Yes, remove it"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleteConfirm(false)}
        />
      )}

      {userToRemove && (
        <ConfirmDialog
          title="Remove user from organisation"
          body={`Remove ${userToRemove.name || userToRemove.email} from "${org.name}"? They will keep their account but lose access to this organisation's data.`}
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => handleRemoveUser(userToRemove)}
          onCancel={() => setUserToRemove(null)}
        />
      )}
    </>
  );
}
