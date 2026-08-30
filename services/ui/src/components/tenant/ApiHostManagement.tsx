/**
 * Platform Management panel for widget embedding hosts.
 *
 * Registers LEO_HOST_ID records and the four mandatory artefacts.
 *
 * Atlas trace:
 *   DO: DO-6F6771E5
 *   DI: DI-14809BB8
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6F6771E5")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import {
  ARTEFACT_KEYS,
  acknowledgeSdkHostIfu,
  listSdkHosts,
  recordSdkHostArtefact,
  registerSdkHost,
  type ArtefactKey,
  type SdkHostRecord,
} from "@/lib/api/sdkGovernance";

const ARTEFACT_LABELS: Record<ArtefactKey, string> = {
  saas_embedding_agreement: "SaaS embedding agreement",
  dpa: "Data processing agreement",
  dcb0129_reference: "DCB0129 safety case",
  ifu_acknowledged: "Instructions for use",
};

function plainError(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function ApiHostManagement() {
  const [hosts, setHosts] = useState<SdkHostRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHosts(await listSdkHosts());
    } catch (err) {
      setError(plainError(err, "Unable to load API hosts. Please retry."));
      setHosts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        This list lives in the running API. It is cleared when the API
        restarts. Production tokens stay blocked until all four artefacts
        are on file.
      </Alert>
      <RegisterForm onRegistered={refresh} />
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
      {loading ? (
        <Box sx={{ py: 4, display: "flex", justifyContent: "center" }}>
          <CircularProgress aria-label="Loading API hosts" />
        </Box>
      ) : (
        <HostList hosts={hosts} onChanged={refresh} />
      )}
    </Box>
  );
}

function RegisterForm({ onRegistered }: { onRegistered: () => Promise<void> }) {
  const [hostId, setHostId] = useState("");
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await registerSdkHost({
        host_id: hostId.trim(),
        name: name.trim(),
        contact: contact.trim(),
      });
      setHostId("");
      setName("");
      setContact("");
      await onRegistered();
    } catch (err) {
      setError(plainError(err, "Unable to register this host. Please retry."));
    } finally {
      setSaving(false);
    }
  }

  const canSubmit = hostId.trim() && name.trim() && contact.trim() && !saving;

  return (
    <Paper sx={{ p: 2, mb: 2 }} data-testid="api-hosts-register">
      <Typography variant="subtitle1" component="h2" sx={{ mb: 1 }}>
        Register an API host
      </Typography>
      <Stack spacing={1.5}>
        <TextField
          label="Host id"
          value={hostId}
          onChange={(e) => setHostId(e.target.value)}
          placeholder="HOST_LEO_CHAT_APP"
          size="small"
          required
        />
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          size="small"
          required
        />
        <TextField
          label="Contact"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          placeholder="you@mizaic.com"
          size="small"
          required
        />
        {error && <Alert severity="error">{error}</Alert>}
        <Button
          variant="contained"
          onClick={() => void onSubmit()}
          disabled={!canSubmit}
        >
          {saving ? "Registering" : "Register host"}
        </Button>
      </Stack>
    </Paper>
  );
}

function HostList({
  hosts,
  onChanged,
}: {
  hosts: SdkHostRecord[];
  onChanged: () => Promise<void>;
}) {
  if (!hosts.length) {
    return (
      <Alert severity="info" data-testid="api-hosts-list">
        No API hosts are registered yet. Use the form above to add one.
      </Alert>
    );
  }
  return (
    <Stack spacing={2} data-testid="api-hosts-list">
      {hosts.map((host) => (
        <HostCard key={host.host_id} host={host} onChanged={onChanged} />
      ))}
    </Stack>
  );
}

function HostCard({
  host,
  onChanged,
}: {
  host: SdkHostRecord;
  onChanged: () => Promise<void>;
}) {
  return (
    <Paper sx={{ p: 2 }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Box>
          <Typography variant="subtitle1" component="h3">
            {host.host_id}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {host.name} - {host.contact}
          </Typography>
        </Box>
        <Chip
          size="small"
          color={host.is_production_ready ? "success" : "warning"}
          label={host.is_production_ready ? "Ready for tokens" : "Not ready"}
        />
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        {ARTEFACT_KEYS.map((key) => (
          <Chip
            key={key}
            size="small"
            variant={host.artefacts[key] ? "filled" : "outlined"}
            label={ARTEFACT_LABELS[key]}
          />
        ))}
      </Stack>
      <ArtefactForm hostId={host.host_id} onChanged={onChanged} />
      <IfuForm hostId={host.host_id} onChanged={onChanged} />
    </Paper>
  );
}

function ArtefactForm({
  hostId,
  onChanged,
}: {
  hostId: string;
  onChanged: () => Promise<void>;
}) {
  const [artefact, setArtefact] = useState<ArtefactKey>("saas_embedding_agreement");
  const [evidence, setEvidence] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await recordSdkHostArtefact(hostId, artefact, evidence.trim());
      setEvidence("");
      await onChanged();
    } catch (err) {
      setError(plainError(err, "Unable to record this artefact. Please retry."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      <TextField
        select
        label="Artefact"
        size="small"
        value={artefact}
        onChange={(e) => setArtefact(e.target.value as ArtefactKey)}
      >
        {ARTEFACT_KEYS.map((key) => (
          <MenuItem key={key} value={key}>
            {ARTEFACT_LABELS[key]}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Evidence link"
        size="small"
        value={evidence}
        onChange={(e) => setEvidence(e.target.value)}
        placeholder="https://..."
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Button
        size="small"
        variant="outlined"
        disabled={!evidence.trim() || saving}
        onClick={() => void onSubmit()}
      >
        Record artefact
      </Button>
    </Stack>
  );
}

function IfuForm({
  hostId,
  onChanged,
}: {
  hostId: string;
  onChanged: () => Promise<void>;
}) {
  const [version, setVersion] = useState("v1.0.0");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await acknowledgeSdkHostIfu(hostId, version.trim());
      await onChanged();
    } catch (err) {
      setError(plainError(err, "Unable to record the IFU acknowledgement."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={1}>
      <TextField
        label="Instructions for Use version"
        size="small"
        value={version}
        onChange={(e) => setVersion(e.target.value)}
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Button
        size="small"
        variant="outlined"
        disabled={!version.trim() || saving}
        onClick={() => void onSubmit()}
      >
        Record IFU acknowledgement
      </Button>
    </Stack>
  );
}
