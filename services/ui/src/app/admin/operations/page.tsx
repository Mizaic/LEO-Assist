"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import Stack from "@mui/material/Stack";
import { useRouter } from "next/navigation";

interface QuickStats {
  pendingReview: number;
  surfaceFormPending: number;
  trainingCandidates: number;
  goldLabels: number;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function loadQuickStats(): Promise<QuickStats> {
  const result = await fetchJson<{
    metrics_by_stage: Record<string, Record<string, number>>;
    surface_form_tasks_pending?: number;
    training_candidates?: number;
    gold_labels?: number;
  }>("/api/operations/metrics").catch(() => null);

  let pending = 0;
  if (result) {
    for (const stage of Object.values(result.metrics_by_stage)) {
      pending += stage.pending ?? 0;
    }
  }

  return {
    pendingReview:      pending,
    surfaceFormPending: result?.surface_form_tasks_pending ?? 0,
    trainingCandidates: result?.training_candidates ?? 0,
    goldLabels:         result?.gold_labels ?? 0,
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
        Fix coding, manage verification examples, then run the model against patient data.
      </Typography>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/operations/reviews")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <FactCheckOutlinedIcon color="warning" />
                  <Chip size="small" variant="outlined" label="Step 1" sx={{ fontSize: "0.7rem" }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Things to check</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Fix coding, context, and surface-form review tasks.
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Chip size="small" color={stats?.pendingReview ? "warning" : "default"} label={`${stats?.pendingReview ?? 0} pending`} />
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
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <SchoolOutlinedIcon color="success" />
                  <Chip size="small" variant="outlined" label="Step 2" sx={{ fontSize: "0.7rem" }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Verification examples</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  View candidates and verified examples used to train the model.
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Chip size="small" label={`${stats?.trainingCandidates ?? 0} candidates`} />
                  <Chip size="small" color={stats?.goldLabels ? "success" : "default"} label={`${stats?.goldLabels ?? 0} verified`} />
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => router.push("/admin/operations/run")}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <PlayCircleOutlineIcon color="primary" />
                  <Chip size="small" variant="outlined" label="Step 3" sx={{ fontSize: "0.7rem" }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight={700}>Run the AI</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Run the model against patient data — reprocess a patient, encounter, or GP list.
                </Typography>
                <Chip size="small" label="Pathway runner" />
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
