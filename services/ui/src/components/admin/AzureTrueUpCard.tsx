/**
 * Atlas trace:
 *   DI: DI-3E297B23
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
 */
"use client";

import React, { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

const ACCOUNT_NOTE =
  "Azure is the whole shared account. Our number is this environment only.";

interface TrueUpCheck {
  date?: string;
  ourInputTokens?: number;
  ourOutputTokens?: number;
  azurePromptTokens?: number;
  azureCompletionTokens?: number;
  ourCostUsd?: number;
  azureCostGbp?: number;
  status?: string;
}

interface TrueUpResponse {
  check: TrueUpCheck | null;
  note: string;
}

export default function AzureTrueUpCard() {
  const [data, setData] = useState<TrueUpResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/pricing/true-up", { credentials: "include" })
      .then(async (r) => {
        if (!r.ok) throw new Error("Could not load the Azure check.");
        return r.json();
      })
      .then((body: TrueUpResponse) => {
        if (!cancelled) setData(body);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card variant="outlined" sx={{ mb: 3, borderRadius: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={700}>
          Daily Azure check
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {ACCOUNT_NOTE}
        </Typography>
        {loading ? <CircularProgress size={20} /> : null}
        {error ? <Alert severity="warning">{error}</Alert> : null}
        {!loading && data && !data.check ? (
          <Typography variant="body2" color="text.disabled">
            No daily check has been stored yet.
          </Typography>
        ) : null}
        {data?.check ? <TrueUpFigures check={data.check} /> : null}
      </CardContent>
    </Card>
  );
}

function TrueUpFigures({ check }: { check: TrueUpCheck }) {
  const ourTokens = (check.ourInputTokens ?? 0) + (check.ourOutputTokens ?? 0);
  const azureTokens =
    (check.azurePromptTokens ?? 0) + (check.azureCompletionTokens ?? 0);
  return (
    <Stack spacing={0.5}>
      <Typography variant="body2">Last check: {check.date ?? "unknown"}</Typography>
      <Typography variant="body2">
        Our tokens: {ourTokens.toLocaleString()} · Azure tokens:{" "}
        {azureTokens.toLocaleString()}
      </Typography>
      <Typography variant="body2">
        Our cost: ${(check.ourCostUsd ?? 0).toFixed(4)} · Azure bill: GBP{" "}
        {(check.azureCostGbp ?? 0).toFixed(2)}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Status: {check.status ?? "unknown"}
      </Typography>
    </Stack>
  );
}

export { ACCOUNT_NOTE };
