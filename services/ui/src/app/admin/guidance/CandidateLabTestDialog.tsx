/**
 * Lab bitmap test dialog -- choose compiled version, pick cases, live progress.
 * Atlas: DO-599B9828 / DI-8DD23CE2. Pins ruleset_version per run; live pointer unchanged.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
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
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { ProgressStrip } from "@leo/design-system";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import type {
  CandidateTestSummary,
  VersionEntry,
} from "./bitmapLifecycleHelpers";
import {
  defaultLabTestVersion,
  formatVersionMeta,
} from "./bitmapLifecycleHelpers";
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

type Stage = "version" | "pick" | "running" | "done";

interface Props {
  open: boolean;
  versions: VersionEntry[];
  preferredVersion?: string | null;
  onClose: () => void;
  onComplete: (summary: CandidateTestSummary) => void;
}

export default function CandidateLabTestDialog({
  open,
  versions,
  preferredVersion,
  onClose,
  onComplete,
}: Props) {
  const [stage, setStage] = useState<Stage>("version");
  const [rulesetVersion, setRulesetVersion] = useState("");
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
    setStage("version");
    setRulesetVersion(defaultLabTestVersion(versions, preferredVersion));
    setSelected(new Set());
    setSheet(null);
    setScores({});
    setError(null);
    setSbarId(null);
    setSbarTitle("");
  }, [preferredVersion, versions]);

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
    if (!selectedCount || !rulesetVersion) return;
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
        rulesetVersion,
        isOpen: () => openRef.current,
        onSheet: (updater) => {
          latest = updater(latest);
          if (openRef.current) setSheet(latest);
        },
      });
      if (!openRef.current) return;
      const finished = { ...latest, done: true };
      setSheet(finished);
      const { summary, byCase } = await scoreSheetItems(
        finished.items,
        rulesetVersion,
      );
      if (!openRef.current) return;
      setScores(byCase);
      setStage("done");
      onComplete(summary);
    } catch {
      if (openRef.current) {
        setError("Could not finish the Lab bitmap test. Please try again.");
        setStage("pick");
      }
    }
  }

  function handleClose() {
    if (stage === "running") openRef.current = false;
    onClose();
  }

  async function openSbar(
    caseId: string,
    runId: string | undefined,
    title: string,
  ) {
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
    stage === "running"
      ? "Work in background"
      : stage === "done"
        ? "Done"
        : "Cancel";

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
          Test with Lab patients
          <Typography variant="body2" color="text.secondary" component="div">
            Runs the real pipeline against a chosen compiled bitmap. Live care
            stays on the current version.
          </Typography>
        </DialogTitle>
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          {stage === "version" && (
            <VersionBody
              versions={versions}
              value={rulesetVersion}
              onChange={setRulesetVersion}
            />
          )}
          {stage === "pick" && (
            <PickBody
              rulesetVersion={rulesetVersion}
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
              rulesetVersion={rulesetVersion}
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
          {stage === "pick" && (
            <Button onClick={() => setStage("version")}>Back</Button>
          )}
          <Button onClick={handleClose}>{dismissLabel}</Button>
          {stage === "version" && (
            <Button
              variant="contained"
              disabled={!rulesetVersion || !versions.length}
              onClick={() => setStage("pick")}
              data-testid="candidate-lab-test-choose-version"
            >
              Continue
            </Button>
          )}
          {stage === "pick" && (
            <Button
              variant="contained"
              disabled={!selectedCount || loadingCases || !rulesetVersion}
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

function VersionBody(props: {
  versions: VersionEntry[];
  value: string;
  onChange: (version: string) => void;
}) {
  const { versions, value, onChange } = props;
  if (!versions.length) {
    return (
      <Alert severity="info" data-testid="candidate-lab-test-version">
        No compiled versions yet. Compile a candidate first.
      </Alert>
    );
  }
  return (
    <Stack spacing={1.5} data-testid="candidate-lab-test-version">
      <Typography variant="body2" color="text.secondary">
        Choose which compiled bitmap to test. Each Lab run pins that version
        for the pipeline only. The live version is not changed.
      </Typography>
      <FormControl fullWidth size="small">
        <InputLabel id="lab-test-bitmap-label">Bitmap version</InputLabel>
        <Select
          labelId="lab-test-bitmap-label"
          label="Bitmap version"
          value={value}
          onChange={(e) => onChange(String(e.target.value))}
          data-testid="candidate-lab-test-version-select"
        >
          {versions.map((v) => (
            <MenuItem key={v.version} value={v.version}>
              <Box>
                <Typography
                  component="span"
                  sx={{ fontFamily: "monospace", fontSize: 13 }}
                >
                  {v.version}
                </Typography>
                {v.active ? " (live)" : ""}
                {formatVersionMeta(v) ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                  >
                    {formatVersionMeta(v)}
                  </Typography>
                ) : null}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Stack>
  );
}

function PickBody(props: {
  rulesetVersion: string;
  loading: boolean;
  cases: LabCase[];
  selected: Set<string>;
  caseIds: string[];
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const {
    rulesetVersion,
    loading,
    cases,
    selected,
    caseIds,
    onToggle,
    onSelectAll,
    onClear,
  } = props;
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
        Testing bitmap{" "}
        <span style={{ fontFamily: "monospace" }}>{rulesetVersion}</span>.
        Choose which Lab patients to run.
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button size="small" onClick={onSelectAll}>
          All
        </Button>
        <Button size="small" onClick={onClear}>
          Clear
        </Button>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ alignSelf: "center" }}
        >
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
  rulesetVersion: string;
  sheet: MultiRunSheet;
  counts: ReturnType<typeof progressCounts>;
  scores: Record<string, CaseGoldScore>;
  stage: Stage;
  sbarBusy: boolean;
  onViewSbar: (caseId: string, runId: string | undefined, title: string) => void;
}) {
  const { rulesetVersion, sheet, counts, scores, stage, sbarBusy, onViewSbar } =
    props;
  return (
    <Stack spacing={1.5} data-testid="candidate-lab-test-run-body">
      <Typography variant="body2" color="text.secondary">
        Bitmap{" "}
        <span style={{ fontFamily: "monospace" }}>{rulesetVersion}</span>
      </Typography>
      <ProgressStrip
        label={
          stage === "done"
            ? counts.running + counts.queued > 0
              ? "Stopped waiting -- some still in flight"
              : "Finished"
            : "Running Lab patients"
        }
        value={counts.terminal}
        total={Math.max(sheet.items.length, 1)}
        subtitle={`${counts.terminal} done · ${counts.running} running · ${counts.queued} queued · ${counts.failed} failed`}
        tone={
          counts.failed > 0
            ? "warning"
            : stage === "done" && counts.running + counts.queued === 0
              ? "positive"
              : "neutral"
        }
      />
      <Stack spacing={1}>
        {sheet.items.map((item) => (
          <Stack
            key={item.caseId}
            direction="row"
            spacing={1}
            alignItems="center"
            data-testid={`candidate-lab-test-case-${item.caseId}`}
          >
            <Typography variant="body2" sx={{ flex: 1 }}>
              {item.title || item.caseId}
            </Typography>
            <Typography
              variant="caption"
              color={goldScoreColor(scores[item.caseId] || "pending")}
            >
              {scores[item.caseId] || item.status}
            </Typography>
            {stage === "done" && item.status === "completed" ? (
              <Button
                size="small"
                disabled={sbarBusy}
                onClick={() =>
                  void onViewSbar(item.caseId, item.runId, item.title || item.caseId)
                }
              >
                View SBAR
              </Button>
            ) : null}
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
