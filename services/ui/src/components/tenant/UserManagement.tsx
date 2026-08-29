/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-35D11EED
 *   DI: DI-A94D6E99
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-35D11EED")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import {
  createGroup, deleteGroup, deleteUser, forceLogoutUser, getEntraCapability,
  listGroupMembers, listGroups, listOrgs, listRoles, listUsers,
  addGroupMember, removeGroupMember,
  type EntraCapability, type Group, type User,
} from "@/lib/api/admin";
import ConfirmDialog from "@/components/ConfirmDialog";
import GroupsPanel, { GroupCreateDialog } from "@/components/tenant/GroupsPanel";
import PeopleList from "@/components/tenant/PeopleList";
import UserEditDialog from "@/components/tenant/UserEditDialog";
import UserInviteDialog from "@/components/tenant/UserInviteDialog";
import UserMemberDialog from "@/components/tenant/UserMemberDialog";

export default function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);
  const [roles, setRoles] = useState<{ name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
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
  const [entraCapability, setEntraCapability] = useState<EntraCapability | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, g, o, r] = await Promise.all([
        listUsers(), listGroups(), listOrgs(), listRoles(),
      ]);
      setUsers(u);
      setGroups(g);
      setOrgs(o.map((x) => ({ id: x.id, name: x.name })));
      setRoles(r.map((x) => ({ name: x.name })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load people and groups.");
    } finally {
      setLoading(false);
    }
    getEntraCapability().then(setEntraCapability).catch(() => setEntraCapability(null));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreateGroup = async () => {
    if (!groupAddName.trim()) return;
    setGroupAddSubmitting(true);
    try {
      await createGroup({
        name: groupAddName.trim(),
        description: groupAddDesc.trim() || undefined,
        org_id: groupAddOrgId || undefined,
      });
      setGroupAddOpen(false);
      setGroupAddName("");
      setGroupAddDesc("");
      setGroupAddOrgId("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the group.");
    } finally {
      setGroupAddSubmitting(false);
    }
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
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : (
        <Grid container spacing={4}>
          <PeopleList
            users={users}
            filteredUsers={filteredUsers}
            userSearch={userSearch}
            setUserSearch={setUserSearch}
            onInvite={() => setInviteOpen(true)}
            onEdit={setEditUser}
            onLogout={setLogoutConfirm}
            onDeactivate={setDeactivateConfirm}
          />
          <GroupsPanel
            groups={groups}
            onCreate={() => setGroupAddOpen(true)}
            onMembers={setMemberDialog}
            onDelete={setGroupDeleteConfirm}
          />
        </Grid>
      )}
      {inviteOpen && (
        <UserInviteDialog
          orgs={orgs}
          groups={groups}
          roles={roles}
          entraCapability={entraCapability}
          onClose={() => setInviteOpen(false)}
          onSaved={() => { setInviteOpen(false); load(); }}
          onError={setError}
        />
      )}
      {editUser && (
        <UserEditDialog
          user={editUser}
          orgs={orgs}
          groups={groups}
          onClose={() => setEditUser(null)}
          onSaved={() => { setEditUser(null); load(); }}
          onError={setError}
        />
      )}
      <GroupCreateDialog
        open={groupAddOpen}
        name={groupAddName}
        desc={groupAddDesc}
        orgId={groupAddOrgId}
        orgs={orgs}
        submitting={groupAddSubmitting}
        setName={setGroupAddName}
        setDesc={setGroupAddDesc}
        setOrgId={setGroupAddOrgId}
        onClose={() => setGroupAddOpen(false)}
        onSave={handleCreateGroup}
      />
      {memberDialog && (
        <UserMemberDialog
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
      {logoutConfirm && (
        <ConfirmDialog
          title="Sign this person out"
          body={`This will sign "${logoutConfirm.name || logoutConfirm.email}" out of all devices right now. They can log back in.`}
          confirmLabel="Sign them out"
          variant="danger"
          onConfirm={async () => {
            try {
              await forceLogoutUser(logoutConfirm.email);
              setLogoutConfirm(null);
              load();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Could not log this person out.");
            }
          }}
          onCancel={() => setLogoutConfirm(null)}
        />
      )}
      {deactivateConfirm && (
        <ConfirmDialog
          title="Remove this person"
          body={`Remove "${deactivateConfirm.name || deactivateConfirm.email}" from LEO? They will not be able to log in any more. Their history is kept.`}
          confirmLabel="Yes, remove them"
          variant="danger"
          onConfirm={async () => {
            try {
              await deleteUser(deactivateConfirm.email);
              setDeactivateConfirm(null);
              load();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Could not remove this person.");
            }
          }}
          onCancel={() => setDeactivateConfirm(null)}
        />
      )}
      {groupDeleteConfirm && (
        <ConfirmDialog
          title="Delete this group"
          body={`Delete "${groupDeleteConfirm.name}"? People in the group will not be deleted -- they just leave this group.`}
          confirmLabel="Yes, delete it"
          variant="danger"
          onConfirm={async () => {
            try {
              await deleteGroup(groupDeleteConfirm.id);
              setGroupDeleteConfirm(null);
              load();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Could not remove this group.");
            }
          }}
          onCancel={() => setGroupDeleteConfirm(null)}
        />
      )}
    </Box>
  );
}
