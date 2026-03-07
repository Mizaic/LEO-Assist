"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import ModelTrainingOutlinedIcon from "@mui/icons-material/ModelTrainingOutlined";
import Stack from "@mui/material/Stack";
import { useRouter } from "next/navigation";

interface QuickStats {
  pendingReview: number;
  surfaceFormPending: number;
  trainingCandidates: number;
  goldLabels: number;
  modelVersion: string;
  modelHealth: string;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function loadQuickStats(): Promise<QuickStats> {
  const [metrics, model] = await Promise.allSettled([
    fetchJson<{
      metrics_by_stage: Record<string, Record<string, number>>;
      surface_form_tasks_pending?: number;
      training_candidates?: number;
      gold_labels?: number;
    }>("/api/operations/metrics"),
    fetchJson<{ active_model: { model_version: string; status: string } | null }>("/api/model-registry/status"),
  ]);

  let pending = 0;
  if (metrics.status === "fulfilled") {
    for (const stage of Object.values(metrics.value.metrics_by_stage)) {
      pending += stage.pending ?? 0;
    }
  }

  let version = "--";
  let health = "neutral";
  if (model.status === "fulfilled" && model.value.active_model) {
    version = `v${model.value.active_model.model_version}`;
    health = model.value.active_model.status;
  }

  return {
    pendingReview: pending,
    surfaceFormPending: metrics.status === "fulfilled" ? (metrics.value.surface_form_tasks_pending ?? 0) : 0,
    trainingCandidates: metrics.status === "fulfilled" ? (metrics.value.training_candidates ?? 0) : 0,
    goldLabels: metrics.status === "fulfilled" ? (metrics.value.gold_labels ?? 0) : 0,
    modelVersion: version,
    modelHealth: health,
  };
}

export default function AdminOperationsPage() {
  const router = useRouter();
  const [stats, setStats] = useState<QuickStats | null>(null);

  useEffect(() => {
    loadQuickStats().then(setStats).catch(() => undefined);
    const id = setInterval(() => loadQuickStats().then(setStats).catch(() => undefined), 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
        Operations
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Run the AI, check things to review, view teaching examples, and monitor the AI model.
      </Typography>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/pathways/pd-gold-training-audit")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                  <PlayCircleOutlineIcon color="primary" />
                  <ChevronRightIcon color="action" />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Run the AI</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Start and test pathway workflows.</Typography>
                <Chip size="small" label="Pathway runner" />
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/operations/reviews")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                  <FactCheckOutlinedIcon color="warning" />
                  <ChevronRightIcon color="action" />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Things to check</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Coding, context, and surface-form review tasks.</Typography>
                <Stack direction="row" spacing={1}>
                  <Chip size="small" color="warning" label={`${stats?.pendingReview ?? 0} pending`} />
                  <Chip size="small" label={`${stats?.surfaceFormPending ?? 0} surface forms`} />
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/gold-dataset")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                  <SchoolOutlinedIcon color="success" />
                  <ChevronRightIcon color="action" />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Teaching examples</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>View candidates and verified examples.</Typography>
                <Stack direction="row" spacing={1}>
                  <Chip size="small" label={`${stats?.trainingCandidates ?? 0} candidates`} />
                  <Chip size="small" color="success" label={`${stats?.goldLabels ?? 0} verified`} />
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/models")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                  <ModelTrainingOutlinedIcon color="info" />
                  <ChevronRightIcon color="action" />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>AI model</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Check model version and deployment status.</Typography>
                <Chip size="small" label={`Model ${stats?.modelVersion ?? "--"} (${stats?.modelHealth ?? "unknown"})`} />
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
