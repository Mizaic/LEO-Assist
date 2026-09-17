/**
 * Atlas trace:
 *   DI: DI-6D87C32F
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-6D87C32F")
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface Quota {
  orgId: string;
  orgName?: string;
  monthlyLimit: number;
}

export default function EncounterQuotaCard() {
  const [quotas, setQuotas] = useState<Quota[]>([]);
  const [orgId, setOrgId] = useState("");
  const [orgName, setOrgName] = useState("");
  const [limit, setLimit] = useState("100");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch("/api/pricing/encounter-quotas", { credentials: "include" });
    if (!r.ok) throw new Error("Could not load encounter limits.");
    const body = await r.json();
    setQuotas(body.quotas ?? []);
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setErr(e.message));
  }, [load]);

  const save = async () => {
    setMsg(null);
    setErr(null);
    const r = await fetch(`/api/pricing/orgs/${encodeURIComponent(orgId)}/encounter-quota`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthlyLimit: Number(limit), orgName }),
    });
    if (!r.ok) {
      setErr("Could not save the encounter limit.");
      return;
    }
    setMsg("Saved. This is a soft limit. Care is not stopped.");
    await load();
  };

  return (
    <Card variant="outlined" sx={{ mb: 3, borderRadius: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={700}>
          Soft encounter limit
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Set how many referrals a customer may process this month. We email if they go
          over limit. We do not stop clinical work.
        </Typography>
        {err ? <Alert severity="warning" sx={{ mb: 1 }}>{err}</Alert> : null}
        {msg ? <Alert severity="success" sx={{ mb: 1 }}>{msg}</Alert> : null}
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
          <TextField
            size="small"
            label="Customer id"
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
          />
          <TextField
            size="small"
            label="Customer name"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
          />
          <TextField
            size="small"
            label="Monthly limit"
            type="number"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
          <Button variant="contained" onClick={save} disabled={!orgId}>
            Save limit
          </Button>
        </Stack>
        {quotas.map((q) => (
          <Typography key={q.orgId} variant="body2">
            {q.orgName || q.orgId}: {q.monthlyLimit} referrals a month
          </Typography>
        ))}
      </CardContent>
    </Card>
  );
}
