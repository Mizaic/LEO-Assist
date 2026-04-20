"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  listEntraGroups,
  listRoles,
  type EntraCapability,
  type EntraGroup,
} from "@/lib/api/admin";
import BindGroupDialog from "@/components/tenant/BindGroupDialog";

interface Props {
  capability: EntraCapability | null;
}

export default function EntraGroupPicker({ capability }: Props) {
  const [prefix, setPrefix] = useState("");
  const [groups, setGroups] = useState<EntraGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bindTarget, setBindTarget] = useState<EntraGroup | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [rolesError, setRolesError] = useState<string | null>(null);

  const canList = capability?.can_list_groups ?? false;

  useEffect(() => {
    if (!canList) {
      setRoles([]);
      return;
    }
    listRoles()
      .then((rs) => setRoles(rs.map((r) => r.name)))
      .catch((e) => setRolesError(e instanceof Error ? e.message : "Could not load LEO roles"));
  }, [canList]);

  const search = useMemo(
    () => async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await listEntraGroups(prefix.trim(), 50);
        setGroups(res.groups || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load Entra groups");
      } finally {
        setLoading(false);
      }
    },
    [prefix]
  );

  if (!canList) {
    return (
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
          Entra security groups
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browsing Entra groups requires <code>Group.Read.All</code>. Once your
          Entra admin grants this permission, you will be able to bind LEO
          roles to existing security groups from here.
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Entra security groups
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Browse security groups from your Entra tenant and bind them to a LEO
        role. Members of a bound group automatically receive the role on
        sign-in -- no manual assignment needed.
      </Typography>

      <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
        <TextField
          size="small"
          placeholder="Filter by name (starts with...)"
          fullWidth
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") search();
          }}
        />
        <Button variant="contained" size="small" onClick={search} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </Button>
      </Box>

      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
      {rolesError && <Alert severity="warning" sx={{ mb: 2 }}>{rolesError}</Alert>}
      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
          <CircularProgress aria-label="Loading groups" size={24} />
        </Box>
      )}
      {!loading && groups.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No groups loaded yet. Use the search box above to browse the tenant.
        </Typography>
      )}
      {!loading && groups.length > 0 && (
        <Stack spacing={1}>
          {groups.map((g) => (
            <Paper
              key={g.id}
              variant="outlined"
              sx={{ px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.5 }}
            >
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }} noWrap>
                  {g.displayName}
                </Typography>
                {g.description && (
                  <Typography variant="caption" color="text.secondary">
                    {g.description}
                  </Typography>
                )}
              </Box>
              <Chip
                size="small"
                variant="outlined"
                label={g.securityEnabled ? "Security" : "Mail"}
                sx={{ flexShrink: 0 }}
              />
              <Button
                size="small"
                variant="outlined"
                onClick={() => setBindTarget(g)}
                disabled={roles.length === 0}
              >
                Bind to LEO role
              </Button>
            </Paper>
          ))}
        </Stack>
      )}

      {bindTarget && (
        <BindGroupDialog
          group={bindTarget}
          roleNames={roles}
          onClose={() => setBindTarget(null)}
          onBound={() => {
            setBindTarget(null);
          }}
        />
      )}
    </Paper>
  );
}
