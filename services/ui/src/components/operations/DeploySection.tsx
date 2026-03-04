"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
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
      .catch(() => setError("Could not load AI information. Please try again."));
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
    <Stack gap={1.5}>
      {/* Current model */}
      <Card variant="outlined">
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1 }}>
            <StatusDot
              variant={model?.status === "active" ? "ok" : model ? "warn" : "neutral"}
              label={model ? "The AI is running" : "No AI is live"}
            />
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              {model ? `Current AI: version ${model.model_version}` : "No AI is live yet"}
            </Typography>
          </Stack>

          {model ? (
            <ActiveModelDetail model={model} totalVersions={data.total_versions} />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: 13 }}>
              Teach and test an AI, then make it live.
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
      <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 1.5 }}>
        <Chip label={model.status} color={statusColor} size="small" />
        <Chip
          label={`${totalVersions} ${totalVersions === 1 ? "version" : "versions"}`}
          size="small"
          variant="outlined"
        />
        {model.promoted_at && (
          <Chip
            label={`Made live ${new Date(model.promoted_at).toLocaleDateString()}`}
            size="small"
            variant="outlined"
          />
        )}
      </Stack>

      <Stack direction="row" gap={2} flexWrap="wrap">
        <MetricPair
          label="Training accuracy"
          tooltip="How often the AI got the right answer during training"
          value={model.offline_precision}
        />
        <MetricPair
          label="Training completeness"
          tooltip="How many real items the AI found during training"
          value={model.offline_recall}
        />
        <MetricPair
          label="Live test accuracy"
          tooltip="How often the AI got the right answer in the safety test"
          value={model.canary_precision}
        />
        <MetricPair
          label="Live test completeness"
          tooltip="How many real items the AI found in the safety test"
          value={model.canary_recall}
        />
      </Stack>

      {model.notes && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          {model.notes}
        </Typography>
      )}
    </>
  );
}

function MetricPair({
  label,
  tooltip,
  value,
}: {
  label: string;
  tooltip?: string;
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

  const content = (
    <Box sx={{ minWidth: 80 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontSize: 11, display: "block", lineHeight: 1.2 }}>
        {label}
      </Typography>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, color, lineHeight: 1.3 }}>
        {display}
      </Typography>
    </Box>
  );

  return tooltip ? <Tooltip title={tooltip} arrow>{content}</Tooltip> : content;
}
