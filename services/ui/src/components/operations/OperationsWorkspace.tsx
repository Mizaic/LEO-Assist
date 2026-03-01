"use client";

import { useState } from "react";
import { Box, Tab, Tabs, Typography } from "@mui/material";
import PipelinePanel from "@/components/PipelinePanel";
import ClassificationReviewPanel from "@/components/classification-review/ClassificationReviewPanel";
import AnchorReviewPanel from "@/components/anchor-review/AnchorReviewPanel";
import HITLTasksPanel from "@/components/operations/HITLTasksPanel";
import ModelLifecyclePanel from "@/components/operations/ModelLifecyclePanel";
import LabelVerificationPanel from "@/components/operations/LabelVerificationPanel";
import TrainingDataPanel from "@/components/operations/TrainingDataPanel";

type OperationsTab =
  | "pipeline"
  | "classification"
  | "anchor"
  | "exclusion_conflict"
  | "peer_review"
  | "training"
  | "label_review"
  | "models";

const TAB_LABELS: Record<OperationsTab, string> = {
  pipeline: "Pipeline",
  classification: "Classification Review",
  anchor: "Anchor Review",
  exclusion_conflict: "Exclusion Conflicts",
  peer_review: "Peer Review",
  training: "Training Data",
  label_review: "Label Review",
  models: "Model Deployment",
};

export default function OperationsWorkspace({
  initialTab = "pipeline",
}: {
  initialTab?: OperationsTab;
}) {
  const [tab, setTab] = useState<OperationsTab>(initialTab);
  const navigateTab = (t: string) => setTab(t as OperationsTab);

  return (
    <Box sx={{ py: 2 }}>
      <Box sx={{ maxWidth: 1200, mx: "auto", px: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Operations
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Unified workspace for coding, review, exclusion conflicts, peer-review, and model deployment.
        </Typography>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v as OperationsTab)}
          sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
          variant="scrollable"
          scrollButtons="auto"
        >
          {(Object.keys(TAB_LABELS) as OperationsTab[]).map((t) => (
            <Tab key={t} value={t} label={TAB_LABELS[t]} />
          ))}
        </Tabs>
      </Box>

      {tab === "pipeline" && <PipelinePanel onNavigateTab={navigateTab} />}
      {tab === "classification" && <ClassificationReviewPanel />}
      {tab === "anchor" && <AnchorReviewPanel />}
      {tab === "exclusion_conflict" && (
        <HITLTasksPanel
          taskType="exclusion_conflict"
          title="Exclusion Conflicts"
          description="Encounters where two LLM models disagreed on cancer exclusion / confirmation. Reviewer must assign a definitive outcome."
        />
      )}
      {tab === "peer_review" && (
        <HITLTasksPanel
          taskType="peer_review"
          title="Peer Review (10% sample)"
          description="Mandatory 10% peer-review sample of approved coding outputs."
        />
      )}
      {tab === "training" && <TrainingDataPanel />}
      {tab === "label_review" && <LabelVerificationPanel />}
      {tab === "models" && <ModelLifecyclePanel />}
    </Box>
  );
}
