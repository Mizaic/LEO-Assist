/**
 * Candidate Lab test dialog -- pick cases, live poll progress, SBAR drawer.
 *
 * Atlas trace:
 *   DO: DO-599B9828
 *   DI: DI-8DD23CE2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-599B9828")
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { ProgressStrip } from "@leo/design-system";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import type { CandidateTestSummary } from "./bitmapLifecycleHelpers";
import {
  SOFT_CASE_WARN,
  goldScoreColor,
  loadSbarAssessmentId,
  progressCounts,
  scoreSheetItems,
  type CaseGoldScore,
} from "./candidateLabTestHelpers";
import {
  initialMultiSheet,
  runBatchWithLiveProgress,
} from "../validation-lab/labBatchRunner";
import { listCases, type LabCase } from "../validation-lab/labApi";
import type { MultiRunSheet } from "../validation-lab/RunSheetDialog";
import {
  allSelected,
  clearSelection,
  toggleId,
} from "../validation-lab/testPatientSelection";

type Stage = "pick" | "running" | "done";

interface Props {
  open: boolean;
  candidateVersion: string;
  onClose: () => void;
  onComplete: (summary: CandidateTestSummary) => void;
}

export default function CandidateLabTestDialog({
  open,
  candidateVersion,
  onClose,
  onComplete,
}: Props) {
  const [stage, setStage] = useState<Stage>("pick");
  const [cases, setCases] = useState<LabCase[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sheet, setSheet] = useState<MultiRunSheet | null>(null);
  const [scores, setScores] = useState<Record<string, CaseGoldScore>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(false);
  const [sbarId, setSbarId] = useState<string | null>(null);
  const [sbarTitle, setSbarTitle] = useState("");
  const [sbarBusy, setSbarBusy] = useState(false);
  const openRef = useRef(true);

  const reset = useCallback(() => {
    setStage("pick");
    setSelected(new Set());
    setSheet(null);
    setScores({});
    setError(null);
    setSbarId(null);
    setSbarTitle("");
  }, []);

  useEffect(() => {
    if (!open) return;
    openRef.current = true;
    reset();
    setLoadingCases(true);
    void listCases()
      .then((rows) => {
        setCases(rows);
        setSelected(new Set(rows.map((c) => c.id)));
      })
      .catch(() => setError("Could not load Validation Lab cases."))
      .finally(() => setLoadingCases(false));
  }, [open, reset]);

  const caseIds = cases.map((c) => c.id);
  const selectedCount = selected.size;

  async function handleRun() {
    if (!selectedCount) return;
    const ids = caseIds.filter((id) => selected.has(id));
    setError(null);
    setStage("running");
    openRef.current = true;
    let latest: MultiRunSheet = initialMultiSheet(ids, cases);
    setSheet(latest);
    try {
      await runBatchWithLiveProgress({
        caseIds: ids,
        cases,
        rulesetVersion: candidateVersion,
        isOpen: () => openRef.current,
        onSheet: (updater) => {
          latest = updater(latest);
          if (openRef.current) setSheet(latest);
        },
      });
      if (!openRef.current) return;
      const finished = { ...latest, done: true };
      setSheet(finished);
      const { summary, byCase } = await scoreSheetItems(finished.items);
      if (!openRef.current) return;
      setScores(byCase);
      setStage("done");
      onComplete(summary);
    } catch {
      if (openRef.current) {
        setError("Could not finish the candidate Lab test. Please try again.");
        setStage("pick");
      }
    }
  }

  function handleClose() {
    if (stage === "running") {
      openRef.current = false;
    }
    onClose();
  }

  async function openSbar(caseId: string, runId: string | undefined, title: string) {
    if (!runId) return;
    setSbarBusy(true);
    setSbarTitle(title);
    setError(null);
    try {
      const assessmentId = await loadSbarAssessmentId(caseId, runId);
      if (!assessmentId) {
        setError("No SBAR is available for this run yet.");
        setSbarId(null);
        return;
      }
      setSbarId(assessmentId);
    } catch {
      setError("Could not load the SBAR for this run.");
      setSbarId(null);
    } finally {
      setSbarBusy(false);
    }
  }

  const counts = sheet ? progressCounts(sheet.items) : null;
  const dismissLabel =
    stage === "running" ? "Work in background" : stage === "done" ? "Done" : "Cancel";

  return (
    <>
      <Dialog
        open={open}
        onClose={handleClose}
        fullWidth
        maxWidth="sm"
        data-testid="candidate-lab-test-dialog"
      >
        <DialogTitle>
          Test candidate on Lab patients
          <Typography variant="body2" color="text.secondary" component="div">
            Ruleset{" "}
            <span style={{ fontFamily: "monospace" }}>{candidateVersion}</span>
            {" -- "}not live.
          </Typography>
        </DialogTitle>
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          {stage === "pick" && (
            <PickBody
              loading={loadingCases}
              cases={cases}
              selected={selected}
              caseIds={caseIds}
              onToggle={(id) => setSelected((prev) => toggleId(prev, id))}
              onSelectAll={() => setSelected(new Set(caseIds))}
              onClear={() => setSelected(clearSelection())}
            />
          )}
          {(stage === "running" || stage === "done") && sheet && counts && (
            <RunBody
              sheet={sheet}
              counts={counts}
              scores={scores}
              stage={stage}
              sbarBusy={sbarBusy}
              onViewSbar={openSbar}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>{dismissLabel}</Button>
          {stage === "pick" && (
            <Button
              variant="contained"
              disabled={!selectedCount || loadingCases}
              onClick={() => void handleRun()}
              data-testid="candidate-lab-test-run"
            >
              Run {selectedCount} case{selectedCount === 1 ? "" : "s"}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={Boolean(sbarId)}
        onClose={() => setSbarId(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 } } }}
        data-testid="candidate-lab-test-sbar-drawer"
      >
        <Box sx={{ p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <Typography variant="h6" component="h2" sx={{ flex: 1 }}>
              SBAR -- {sbarTitle || "Lab case"}
            </Typography>
            <IconButton
              aria-label="Close SBAR"
              onClick={() => setSbarId(null)}
              size="small"
            >
              <CloseIcon />
            </IconButton>
          </Stack>
          {sbarId ? <LeoSbarHost assessmentId={sbarId} /> : null}
        </Box>
      </Drawer>
    </>
  );
}

function PickBody(props: {
  loading: boolean;
  cases: LabCase[];
  selected: Set<string>;
  caseIds: string[];
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const { loading, cases, selected, caseIds, onToggle, onSelectAll, onClear } =
    props;
  if (loading) {
    return (
      <Typography variant="body2" color="text.secondary">
        Loading Lab cases...
      </Typography>
    );
  }
  if (!cases.length) {
    return (
      <Alert severity="info">
        No Validation Lab cases yet. Create one in Validation Lab first.
      </Alert>
    );
  }
  return (
    <Stack spacing={1.5} data-testid="candidate-lab-test-pick">
      <Typography variant="body2" color="text.secondary">
        Choose which Lab patients to run against this candidate. Each run uses
        the real pipeline with the candidate ruleset pinned.
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button size="small" onClick={onSelectAll}>
          All
        </Button>
        <Button size="small" onClick={onClear}>
          Clear
        </Button>
        <Typography variant="body2" color="text.secondary" sx={{ alignSelf: "center" }}>
          {selected.size} of {cases.length} selected
          {allSelected(caseIds, selected) ? " (all)" : ""}
        </Typography>
      </Stack>
      {selected.size > SOFT_CASE_WARN && (
        <Alert severity="warning">
          Running more than {SOFT_CASE_WARN} cases may take several minutes.
        </Alert>
      )}
      <Stack sx={{ maxHeight: 280, overflow: "auto" }}>
        {cases.map((labCase) => (
          <FormControlLabel
            key={labCase.id}
            control={
              <Checkbox
                checked={selected.has(labCase.id)}
                onChange={() => onToggle(labCase.id)}
                inputProps={{
                  "aria-label": `Select ${labCase.title || labCase.id}`,
                }}
              />
            }
            label={labCase.title || labCase.id}
          />
        ))}
      </Stack>
    </Stack>
  );
}

function RunBody(props: {
  sheet: MultiRunSheet;
  counts: ReturnType<typeof progressCounts>;
  scores: Record<string, CaseGoldScore>;
  stage: Stage;
  sbarBusy: boolean;
  onViewSbar: (caseId: string, runId: string | undefined, title: string) => void;
}) {
  const { sheet, counts, scores, stage, sbarBusy, onViewSbar } = props;
  const label =
    sheet.phase === "queueing" ? "Queueing runs" : "Live pipeline progress";
  const subtitle =
    sheet.phase === "queueing"
      ? `${counts.queued + counts.terminal} started`
      : `${counts.terminal} done · ${counts.running} running · ${counts.queued} queued`;

  return (
    <Stack spacing={2} data-testid="candidate-lab-test-run-body">
      <ProgressStrip
        label={label}
        value={
          sheet.phase === "queueing"
            ? counts.queued + counts.terminal
            : counts.terminal
        }
        total={Math.max(sheet.items.length, 1)}
        subtitle={subtitle}
        tone={
          counts.failed > 0 ? "warning" : sheet.done ? "positive" : "neutral"
        }
      />
      <Stack spacing={0.75} sx={{ maxHeight: 280, overflow: "auto" }}>
        {sheet.items.map((item) => {
          const gold = scores[item.caseId];
          const canView =
            stage === "done" && item.status === "completed" && Boolean(item.runId);
          return (
            <Box
              key={item.caseId}
              sx={{
                display: "flex",
                justifyContent: "space-between",
                gap: 1,
                alignItems: "center",
                py: 0.5,
                borderBottom: "1px solid",
                borderColor: "divider",
              }}
              data-testid={`candidate-lab-test-item-${item.caseId}`}
            >
              <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                {item.title || item.caseId}
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                {gold && gold !== "pending" && (
                  <Typography variant="caption" color={goldScoreColor(gold)}>
                    gold {gold}
                  </Typography>
                )}
                <Typography variant="caption" color="text.secondary">
                  {item.status}
                </Typography>
                {canView && (
                  <Button
                    size="small"
                    disabled={sbarBusy}
                    onClick={() =>
                      onViewSbar(item.caseId, item.runId, item.title || item.caseId)
                    }
                    data-testid={`candidate-lab-test-view-sbar-${item.caseId}`}
                  >
                    View SBAR
                  </Button>
                )}
              </Stack>
            </Box>
          );
        })}
      </Stack>
      {stage === "running" && (
        <Typography variant="body2" color="text.secondary">
          Polling workers every few seconds. You can work in the background;
          runs continue on the server.
        </Typography>
      )}
    </Stack>
  );
}
