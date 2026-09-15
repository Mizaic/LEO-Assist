/**
 * Minimal patient journey builder for milestone document + SBAR playback.
 *
 * Atlas trace:
 *   DI: DI-9DD9E548
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import AddIcon from "@mui/icons-material/Add";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import { ProgressiveReveal, color, radius } from "@leo/design-system";
import { useOrg } from "@/context/OrgContext";
import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import { createEpisode } from "@/lib/missionControlApi";
import {
  JOURNEY_MILESTONES,
  pollMilestoneSbarUntilTerminal,
  startMilestoneSbar,
} from "@/lib/patientDocumentsApi";
import {
  pollDocumentRunUntilTerminal,
  startDocumentRun,
} from "@/lib/documentRunApi";
import type { DocumentRow } from "@/lib/patientEprApi";
import {
  DocumentEditorDialog,
  type DocumentEditorInitial,
} from "./DocumentEditorDialog";

interface Props {
  patientId: string;
  documents: DocumentRow[];
  onDocumentsChanged: () => void;
}

interface SbarHistoryItem {
  id: string;
  label: string;
  scope: string;
}

export function JourneyBuilderPanel({
  patientId,
  documents,
  onDocumentsChanged,
}: Props) {
  const { isPlatformAdmin } = useOrg();
  const [episodeId, setEpisodeId] = useState("");
  const [cancerType, setCancerType] = useState("breast");
  const [milestoneType, setMilestoneType] = useState("referral");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorInitial, setEditorInitial] = useState<DocumentEditorInitial>();
  const [history, setHistory] = useState<SbarHistoryItem[]>([]);
  const [previewAssessmentId, setPreviewAssessmentId] = useState<string | null>(null);

  useEffect(() => {
    const fromDocs = documents.find((d) => d.episode_id)?.episode_id;
    if (fromDocs && !episodeId) setEpisodeId(fromDocs);
  }, [documents, episodeId]);

  const ensureEpisode = useCallback(async () => {
    if (episodeId.trim()) return episodeId.trim();
    const created = await createEpisode({
      patient_id: patientId,
      cancer_type: cancerType,
      status: "active",
    });
    const id = created.episode_id;
    setEpisodeId(id);
    return id;
  }, [cancerType, episodeId, patientId]);

  const handleStartJourney = async () => {
    setError(null);
    setBusy(true);
    try {
      await ensureEpisode();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create episode.");
    } finally {
      setBusy(false);
    }
  };

  const handleAddMilestoneDoc = async () => {
    setError(null);
    setBusy(true);
    try {
      const eid = await ensureEpisode();
      setEditorInitial({
        title: `${milestoneType.replace(/_/g, " ")} document`,
        category: "referral",
        episodeId: eid,
        milestoneType,
      });
      setEditorOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to open document editor.");
    } finally {
      setBusy(false);
    }
  };

  const handleRunDocumentPipeline = async () => {
    setError(null);
    const milestoneDoc = documents
      .filter((d) => d.episode_id === episodeId)
      .sort((a, b) => (b.document_date ?? "").localeCompare(a.document_date ?? ""))[0];
    if (!milestoneDoc?.document_id) {
      setError("Add a document for this episode first.");
      return;
    }
    setBusy(true);
    try {
      const chunks = await fetch(
        `/api/analytics/document-references/${encodeURIComponent(milestoneDoc.document_id)}/resolved-chunks`,
        { credentials: "include" },
      ).then((r) => r.json()) as { chunks?: Array<{ id: string }> };
      const chunkIds = (chunks.chunks ?? []).map((c) => c.id).filter(Boolean);
      if (!chunkIds.length) {
        setError("No chunks found for the selected document.");
        return;
      }
      const started = await startDocumentRun(patientId, {
        document_reference_id: milestoneDoc.document_id,
        chunk_ids: chunkIds,
      });
      const finished = await pollDocumentRunUntilTerminal(patientId, started.run_id);
      if (finished.assessment_id) {
        setHistory((prev) => [
          {
            id: finished.assessment_id!,
            label: "Document pipeline SBAR",
            scope: "referral",
          },
          ...prev,
        ]);
        setPreviewAssessmentId(finished.assessment_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Document pipeline failed.");
    } finally {
      setBusy(false);
    }
  };

  const handlePlayEpisodeSbar = async () => {
    if (!episodeId) {
      setError("Start a journey episode first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const started = await startMilestoneSbar(patientId, episodeId, {
        milestone_type: milestoneType,
        include_rollup: true,
      });
      const finished = await pollMilestoneSbarUntilTerminal(
        patientId,
        episodeId,
        started.run_id,
      );
      if (finished.status === "failed") {
        throw new Error(finished.error_message || "Episode SBAR failed.");
      }
      const items: SbarHistoryItem[] = [];
      if (finished.episode_assessment_id) {
        items.push({
          id: finished.episode_assessment_id,
          label: `Episode SBAR (${milestoneType})`,
          scope: "episode",
        });
      }
      if (finished.rollup_assessment_id) {
        items.push({
          id: finished.rollup_assessment_id,
          label: `Rollup SBAR (${milestoneType})`,
          scope: "rollup",
        });
      }
      setHistory((prev) => [...items, ...prev]);
      setPreviewAssessmentId(finished.episode_assessment_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Episode SBAR failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!isPlatformAdmin) return null;

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: `${radius.md}px`,
        px: 1.5,
        py: 1,
        bgcolor: color.surface.raised,
        flexShrink: 0,
      }}
      data-testid="journey-builder-panel"
    >
      <ProgressiveReveal summary="Build a journey" defaultOpen={false}>
        {error && (
          <Alert severity="error" sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}
        <Stack spacing={1.25}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              label="Episode id"
              value={episodeId}
              onChange={(e) => setEpisodeId(e.target.value)}
              helperText={episodeId ? "Episode linked" : "Create or paste an episode id"}
              sx={{ minWidth: 220, flex: 1 }}
            />
            <TextField
              size="small"
              select
              label="Milestone"
              value={milestoneType}
              onChange={(e) => setMilestoneType(e.target.value)}
              sx={{ minWidth: 160 }}
            >
              {JOURNEY_MILESTONES.map((m) => (
                <MenuItem key={m.id} value={m.id}>
                  {m.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          {!episodeId && (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                select
                label="Cancer type"
                value={cancerType}
                onChange={(e) => setCancerType(e.target.value)}
                sx={{ minWidth: 140 }}
              >
                <MenuItem value="breast">Breast</MenuItem>
                <MenuItem value="lung">Lung</MenuItem>
                <MenuItem value="lower_gi">Lower GI</MenuItem>
              </TextField>
              <Button
                variant="outlined"
                startIcon={busy ? <CircularProgress size={16} /> : <AddIcon />}
                onClick={() => void handleStartJourney()}
                disabled={busy}
                sx={{ textTransform: "none" }}
              >
                Start journey
              </Button>
            </Stack>
          )}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => void handleAddMilestoneDoc()}
              disabled={busy}
              sx={{ textTransform: "none" }}
            >
              Add milestone document
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<PlayArrowOutlinedIcon />}
              onClick={() => void handleRunDocumentPipeline()}
              disabled={busy}
              sx={{ textTransform: "none" }}
            >
              Run document pipeline
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<PlayArrowOutlinedIcon />}
              onClick={() => void handlePlayEpisodeSbar()}
              disabled={busy}
              sx={{ textTransform: "none" }}
            >
              Play episode SBAR
            </Button>
          </Stack>
          {history.length > 0 && (
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {history.map((item) => (
                <Chip
                  key={`${item.scope}:${item.id}`}
                  label={item.label}
                  size="small"
                  clickable
                  onClick={() => setPreviewAssessmentId(item.id)}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </ProgressiveReveal>

      <DocumentEditorDialog
        open={editorOpen}
        patientId={patientId}
        initial={editorInitial}
        onClose={() => setEditorOpen(false)}
        onSaved={() => {
          onDocumentsChanged();
        }}
      />

      <Dialog
        open={Boolean(previewAssessmentId)}
        onClose={() => setPreviewAssessmentId(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>SBAR preview</DialogTitle>
        <DialogContent>
          {previewAssessmentId && (
            <LeoSbarHost assessmentId={previewAssessmentId} testId="journey-sbar" />
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
