"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import {
  getEntraCapability,
  listEntraDomains,
  type EntraCapability,
  type EntraDomain,
} from "@/lib/api/admin";
import EntraGroupPicker from "@/components/tenant/EntraGroupPicker";

const SCOPE_LABELS: Record<string, string> = {
  "https://graph.microsoft.com/Domain.Read.All": "Read tenant domains",
  "https://graph.microsoft.com/User.Read.All": "Search users",
  "https://graph.microsoft.com/Group.Read.All": "Browse security groups",
  "https://graph.microsoft.com/Group.ReadWrite.All": "Create security groups",
  "https://graph.microsoft.com/GroupMember.ReadWrite.All": "Manage group membership",
};

function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope.replace("https://graph.microsoft.com/", "");
}

export default function EntraIntegration() {
  const [capability, setCapability] = useState<EntraCapability | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [domains, setDomains] = useState<EntraDomain[]>([]);
  const [domainsError, setDomainsError] = useState<string | null>(null);
  const [domainsLoading, setDomainsLoading] = useState(false);

  const refreshCapability = useCallback(async () => {
    setLoading(true);
    setCapabilityError(null);
    try {
      const cap = await getEntraCapability();
      setCapability(cap);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not check Microsoft Entra access.";
      setCapabilityError(msg);
      setCapability(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCapability();
  }, [refreshCapability]);

  const canListDomains = capability?.can_list_domains ?? false;

  useEffect(() => {
    if (!canListDomains) {
      setDomains([]);
      return;
    }
    let cancelled = false;
    setDomainsLoading(true);
    setDomainsError(null);
    listEntraDomains()
      .then((res) => {
        if (!cancelled) setDomains(res.domains || []);
      })
      .catch((e) => {
        if (!cancelled) {
          setDomainsError(
            e instanceof Error ? e.message : "Could not list verified domains."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDomainsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canListDomains]);

  const missingScopes = useMemo(() => {
    if (!capability) return [] as string[];
    const granted = new Set(capability.scopes_granted);
    return capability.scopes_required.filter((s) => !granted.has(s));
  }, [capability]);

  if (loading && !capability) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress aria-label="Checking Microsoft Entra access" />
      </Box>
    );
  }

  return (
    <Box>
      <CapabilityBanner
        capability={capability}
        error={capabilityError}
        missingScopes={missingScopes}
        onRefresh={refreshCapability}
      />

      <Stack spacing={3} sx={{ mt: 3 }}>
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
            Verified domains
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            These are the email domains your tenant has verified in Microsoft Entra.
            People with an email at one of these domains can sign in to LEO.
          </Typography>
          {!canListDomains && (
            <Typography variant="body2" color="text.secondary">
              Domain listing is not available until your Entra admin grants{" "}
              <code>Domain.Read.All</code> to LEO.
            </Typography>
          )}
          {canListDomains && domainsLoading && (
            <Box sx={{ display: "flex", py: 2 }}>
              <CircularProgress size={20} aria-label="Loading domains" />
            </Box>
          )}
          {canListDomains && domainsError && (
            <Alert severity="warning">{domainsError}</Alert>
          )}
          {canListDomains && !domainsLoading && !domainsError && domains.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No verified domains were returned for this tenant.
            </Typography>
          )}
          {canListDomains && !domainsLoading && domains.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Domain</TableCell>
                  <TableCell>Default</TableCell>
                  <TableCell>Verified</TableCell>
                  <TableCell>Authentication</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {domains.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>{d.id}</TableCell>
                    <TableCell>
                      {d.isDefault ? <Chip size="small" label="Default" color="primary" /> : "—"}
                    </TableCell>
                    <TableCell>
                      {d.isVerified ? (
                        <CheckCircleOutlineIcon fontSize="small" color="success" />
                      ) : (
                        <ErrorOutlineIcon fontSize="small" color="warning" />
                      )}
                    </TableCell>
                    <TableCell>{d.authenticationType ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>

        <Divider />

        <EntraGroupPicker capability={capability} />
      </Stack>
    </Box>
  );
}

// ------------------------------------------------------------------
// Capability banner
// ------------------------------------------------------------------

function CapabilityBanner({
  capability,
  error,
  missingScopes,
  onRefresh,
}: {
  capability: EntraCapability | null;
  error: string | null;
  missingScopes: string[];
  onRefresh: () => void;
}) {
  if (error || !capability) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={onRefresh}>Retry</Button>
      }>
        <AlertTitle>Could not check Microsoft Entra access</AlertTitle>
        {error ?? "Unknown error"}
      </Alert>
    );
  }

  if (missingScopes.length === capability.scopes_required.length) {
    return (
      <Alert severity="warning">
        <AlertTitle>Microsoft Entra is not connected</AlertTitle>
        Your Entra admin has not granted LEO any of the permissions needed to
        manage users and groups from this portal. You can still add people and
        groups manually in <strong>People &amp; Groups</strong>; sign-in will
        continue to work.
        <Box sx={{ mt: 1 }}>
          <Link
            href={capability.admin_consent_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Grant Microsoft Entra admin consent <OpenInNewIcon fontSize="inherit" />
          </Link>
        </Box>
      </Alert>
    );
  }

  if (missingScopes.length > 0) {
    return (
      <Alert severity="info">
        <AlertTitle>Microsoft Entra is partly connected</AlertTitle>
        Some Entra-driven actions are unavailable until your Entra admin grants
        the missing permissions:
        <Box component="ul" sx={{ mt: 1, mb: 1, pl: 3 }}>
          {missingScopes.map((s) => (
            <li key={s}>
              <Typography variant="body2">{scopeLabel(s)}</Typography>
            </li>
          ))}
        </Box>
        <Link
          href={capability.admin_consent_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Grant the missing permissions <OpenInNewIcon fontSize="inherit" />
        </Link>
      </Alert>
    );
  }

  return (
    <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
      Microsoft Entra is fully connected for tenant{" "}
      <strong>{capability.tenant_id ?? "your tenant"}</strong>. You can search
      Entra users, browse security groups, and create or bind groups from this
      portal.
    </Alert>
  );
}
