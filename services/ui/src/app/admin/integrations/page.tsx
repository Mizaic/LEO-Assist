/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { api } from "@/lib/api";

interface Integration {
  id: string;
  name: string;
  baseUrl: string;
  authType: string;
}

export default function IntegrationsPage() {
  const [items, setItems] = useState<Integration[]>([]);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [authType, setAuthType] = useState("bearer");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const response = await api.get<{ integrations?: Integration[] }>("/admin/integrations");
      setItems(response.integrations ?? []);
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    setError(null);
    try {
      await api.post("/admin/integrations", { name, baseUrl, authType });
      setName("");
      setBaseUrl("");
      setAuthType("bearer");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save integration");
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>Integrations</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Manage registered API integrations used by REST connector nodes in the pathway canvas.
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={1}>
          <TextField size="small" label="Name" value={name} onChange={(e) => setName(e.target.value)} sx={{ flex: 1 }} />
          <TextField size="small" label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} sx={{ flex: 2 }} />
          <TextField size="small" label="Auth type" value={authType} onChange={(e) => setAuthType(e.target.value)} sx={{ width: 140 }} />
          <Button variant="contained" onClick={add}>Add</Button>
        </Stack>
      </Paper>
      <Stack spacing={1}>
        {items.map((item) => (
          <Paper key={item.id} variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="subtitle2">{item.name}</Typography>
            <Typography variant="caption" color="text.secondary">{item.baseUrl} · {item.authType}</Typography>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}

