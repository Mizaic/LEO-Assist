"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import StatusDot from "./StatusDot";
import ModelLifecyclePanel from "./ModelLifecyclePanel";

// -- Types -------------------------------------------------------------------

interface ModelVersion {
  model_name: string;
  model_version: string;
  status: string;
  offline_precision: number | null;
  offline_recall: number | null;
  canary_precision: number | null;
  canary_recall: number | null;
  registered_at: string | null;
  promoted_at: string | null;
  notes: string | null;
}

interface ModelStatus {
  active_model: ModelVersion | null;
  total_versions: number;
}

// -- Fetch -------------------------------------------------------------------

async function loadModelStatus(): Promise<ModelStatus> {
  const res = await fetch("/api/model-registry/status");
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

// -- Component ---------------------------------------------------------------

export default function DeploySection() {
  const [data, setData] = useState<ModelStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadModelStatus()
      .then(setData)
      .catch(() => setError("Could not load model information."));
  }, []);

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!data) {
    return (
      <Stack gap={2}>
        <Skeleton variant="rounded" height={120} />
        <Skeleton variant="rounded" height={300} />
      </Stack>
    );
  }

  const model = data.active_model;

  return (
    <Stack gap={2.5}>
      {/* Current model */}
      <Card>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1.5 }}>
            <StatusDot
              variant={model?.status === "active" ? "ok" : model ? "warn" : "neutral"}
              label={model ? `Model is ${model.status}` : "No model"}
            />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {model ? `Live model: v${model.model_version}` : "No model deployed"}
            </Typography>
          </Stack>

          {model ? (
            <ActiveModelDetail model={model} totalVersions={data.total_versions} />
          ) : (
            <Typography variant="body2" color="text.secondary">
              Train and promote a model to make it live.
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* Full lifecycle panel */}
      <ModelLifecyclePanel />
    </Stack>
  );
}

// -- Sub-component -----------------------------------------------------------

function ActiveModelDetail({
  model,
  totalVersions,
}: {
  model: ModelVersion;
  totalVersions: number;
}) {
  const statusColor =
    model.status === "active" ? "success" : model.status === "canary" ? "warning" : "default";

  return (
    <>
      <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mb: 2 }}>
        <Chip label={model.status} color={statusColor} size="small" />
        <Chip
          label={`${totalVersions} ${totalVersions === 1 ? "version" : "versions"} total`}
          size="small"
          variant="outlined"
        />
        {model.promoted_at && (
          <Chip
            label={`Promoted ${new Date(model.promoted_at).toLocaleDateString()}`}
            size="small"
            variant="outlined"
          />
        )}
      </Stack>

      {/* Metrics */}
      <Stack direction="row" gap={3} flexWrap="wrap">
        <MetricPair
          label="Offline precision"
          value={model.offline_precision}
        />
        <MetricPair
          label="Offline recall"
          value={model.offline_recall}
        />
        <MetricPair
          label="Canary precision"
          value={model.canary_precision}
        />
        <MetricPair
          label="Canary recall"
          value={model.canary_recall}
        />
      </Stack>

      {model.notes && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          {model.notes}
        </Typography>
      )}
    </>
  );
}

function MetricPair({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  const display = value != null ? `${(value * 100).toFixed(1)}%` : "--";
  const color =
    value == null
      ? "text.disabled"
      : value >= 0.9
        ? "success.main"
        : value >= 0.8
          ? "text.primary"
          : "warning.main";

  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 700, color }}>
        {display}
      </Typography>
    </Box>
  );
}
