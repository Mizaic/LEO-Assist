/**
 * Reprocess dialog -- select chunks and re-run the referral pipeline from Care.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DO: DO-158BE606
 *   DI: DI-357A7468
 *   DI: DI-FE423B8D
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";

import { useOrg } from "@/context/OrgContext";
import {
  listResolvedDocumentReferenceChunks,
  type PatientFinderChunk,
} from "@/lib/analyticsApi";
import type { DocumentRow } from "@/lib/patientEprApi";
import {
  pollDocumentRunUntilTerminal,
  startDocumentRun,
  type DocumentRunResponse,
} from "@/lib/documentRunApi";
import RunSheetDialog, {
  type SingleRunSheet,
} from "@/app/admin/validation-lab/RunSheetDialog";

interface Props {
  patientId: string;
  doc: DocumentRow;
  open: boolean;
  onClose: () => void;
  onDocumentsChanged?: (selectDocumentId?: string) => void;
}

function chunkLabel(chunk: PatientFinderChunk): string {
  const body = (chunk.text || chunk.preview || "").trim();
  if (!body) return `Chunk ${chunk.ordinal + 1}`;
  return body.length > 120 ? `${body.slice(0, 120)}...` : body;
}

function chunkRowKey(chunk: PatientFinderChunk): string {
  return `${chunk.ordinal}:${chunk.id}`;
}

export function sheetFromDocumentRun(
  title: string,
  run: DocumentRunResponse | null,
): SingleRunSheet {
  if (!run) {
    return {
      mode: "single",
      caseId: "",
      title,
      status: "starting",
      phases: [],
      terminal: false,
    };
  }
  const terminal = run.status === "completed" || run.status === "failed";
  return {
    mode: "single",
    caseId: "",
    title,
    runId: run.run_id || undefined,
    status: run.status,
    phases: [],
    stages: run.stage_progress,
    llmUsage: run.llm_usage,
    error: run.error_message || undefined,
    terminal,
    assessmentId: run.assessment_id,
    pipelineRunId: run.run_id || undefined,
  };
}

function nextSbarDocumentId(run: DocumentRunResponse | null): string | undefined {
  const id = (run?.assessment_id || "").trim();
  return id ? `assessment:${id}` : undefined;
}

export function DocumentChunkPanel({
  patientId,
  doc,
  open,
  onClose,
  onDocumentsChanged,
}: Props) {
  const { isPlatformAdmin } = useOrg();
  const [chunks, setChunks] = useState<PatientFinderChunk[]>([]);
  const [chunkSourceId, setChunkSourceId] = useState<string>("");
  const [chunkResolution, setChunkResolution] = useState<string>("none");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [activeRun, setActiveRun] = useState<DocumentRunResponse | null>(null);

  const canRun = Boolean(isPlatformAdmin && doc.referral_id);

  useEffect(() => {
    if (!open || !doc.document_id) return;
    setSelected(new Set());
    setError(null);
    setLoading(true);
    listResolvedDocumentReferenceChunks(doc.document_id, doc.referral_id, 500, true)
      .then((resolved) => {
        setChunks(resolved.chunks);
        setChunkSourceId(resolved.source_document_id);
        setChunkResolution(resolved.resolution);
        setSelected(new Set(resolved.chunks.map((c) => chunkRowKey(c))));
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load chunks."),
      )
      .finally(() => setLoading(false));
  }, [open, doc.document_id, doc.referral_id]);

  const allSelected = chunks.length > 0 && selected.size === chunks.length;

  const toggleAll = useCallback(() => {
    setSelected((prev) =>
      prev.size === chunks.length
        ? new Set()
        : new Set(chunks.map((c) => chunkRowKey(c))),
    );
  }, [chunks]);

  const toggleOne = useCallback((rowKey: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rowKey)) next.delete(rowKey);
      else next.add(rowKey);
      return next;
    });
  }, []);

  const selectedIds = useMemo(() => {
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const chunk of chunks) {
      if (!selected.has(chunkRowKey(chunk))) continue;
      if (seen.has(chunk.id)) continue;
      seen.add(chunk.id);
      ids.push(chunk.id);
    }
    return ids;
  }, [chunks, selected]);

  const handleRun = async () => {
    if (!canRun || selectedIds.length === 0) return;
    setRunning(true);
    setRunOpen(true);
    setActiveRun(null);
    onClose();
    try {
      const started = await startDocumentRun(patientId, {
        document_reference_id: chunkSourceId || doc.document_id,
        chunk_ids: selectedIds,
      });
      setActiveRun(started);
      const finalRun = await pollDocumentRunUntilTerminal(
        patientId,
        started.run_id,
        setActiveRun,
      );
      setActiveRun(finalRun);
      onDocumentsChanged?.(nextSbarDocumentId(finalRun));
    } catch (e) {
      setActiveRun({
        run_id: "",
        status: "failed",
        assessment_id: null,
        error_message: e instanceof Error ? e.message : "Pipeline run failed.",
        stage_progress: [],
      });
    } finally {
      setRunning(false);
    }
  };

  if (!isPlatformAdmin) return null;

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        maxWidth="md"
        fullWidth
        data-testid="document-reprocess-dialog"
      >
        <DialogTitle>Reprocess document</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Select chunks to reprocess through the referral pipeline. A new SBAR
            assessment is written to the patient graph for downstream systems.
          </Typography>
          {!doc.referral_id && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              This document is not linked to a referral, so it cannot be reprocessed.
            </Alert>
          )}
          {loading && (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={18} />
              <Typography variant="caption">Loading chunks...</Typography>
            </Stack>
          )}
          {error && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              {error}
            </Alert>
          )}
          {!loading && chunks.length === 0 && !error && (
            <Alert severity="info">
              No pipeline chunks are stored for this referral yet. The file may
              only exist as a PDF or Word URL until ingestion creates chunk text.
            </Alert>
          )}
          {chunks.length > 0 && chunkResolution !== "direct" && (
            <Alert severity="info" sx={{ mb: 1 }}>
              Showing {chunks.length} chunk{chunks.length === 1 ? "" : "s"} from
              the referral bundle or a linked form, not from this PDF file.
            </Alert>
          )}
          {chunks.length > 0 && (
            <>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={allSelected}
                    indeterminate={selected.size > 0 && !allSelected}
                    onChange={toggleAll}
                  />
                }
                label={`Select all (${chunks.length})`}
              />
              <Stack spacing={0.5} sx={{ maxHeight: 360, overflowY: "auto" }}>
                {chunks.map((chunk) => {
                  const rowKey = chunkRowKey(chunk);
                  return (
                    <FormControlLabel
                      key={rowKey}
                      sx={{ alignItems: "flex-start", ml: 0 }}
                      control={
                        <Checkbox
                          checked={selected.has(rowKey)}
                          onChange={() => toggleOne(rowKey)}
                          sx={{ pt: 0.25 }}
                        />
                      }
                      label={
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                          <Box component="span" sx={{ fontWeight: 600, mr: 1 }}>
                            #{chunk.ordinal + 1}
                          </Box>
                          {chunkLabel(chunk)}
                        </Typography>
                      }
                    />
                  );
                })}
              </Stack>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="contained"
            startIcon={
              running ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <PlayArrowOutlinedIcon />
              )
            }
            disabled={!canRun || running || selectedIds.length === 0}
            onClick={() => void handleRun()}
            data-testid="document-run-pipeline"
          >
            Run pipeline on selected chunks
          </Button>
        </DialogActions>
      </Dialog>
      {runOpen ? (
        <RunSheetDialog
          sheet={sheetFromDocumentRun(doc.title, activeRun)}
          showSbarActions={false}
          onClose={() => {
            setRunOpen(false);
            onDocumentsChanged?.(nextSbarDocumentId(activeRun));
          }}
        />
      ) : null}
    </>
  );
}
