/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 *
 * Phase 4 trace (debounced on-commit sandbox replay):
 *   UN: UN-26E57FA1
 *   DI: DI-D801A490
 *   DO: DO-0D8619CE
 *   Risk: R-8B052FB8
 *   VT: VT-B668D256
 */
"use client";

/**
 * Sandbox-only Test Patients panel embedded in the EditRuleDialog.
 *
 * Phase 1 redesign (April 2026):
 *
 *   The previous version offered TWO test surfaces -- a "Live" replay
 *   against the production Redis bitmap, and a "Sandbox" replay against
 *   a throwaway compile of the unsaved draft. The Live card was unsafe
 *   by construction: when the reviewer is editing a rule, the live
 *   bitmap still contains the OLD rule, so testing against it told
 *   the reviewer how the OLD rule performs -- not how their unsaved
 *   change performs. Worse, an auto-replay fired on every logic-tree
 *   edit, so the misleading banner refreshed in real time.
 *
 *   This file now offers exactly one surface: the sandbox. It compiles
 *   the unsaved draft into a throwaway bitmap (terminology
 *   ``compile-draft`` physically refuses anything other than
 *   ``scope_type='custom'``) and replays the saved test patients
 *   through it. The sandbox keys are deleted in ``finally`` server-side.
 *
 *   The compile-time guideline-wide replay still exists, but it lives
 *   on the Bitmap Lifecycle page where the reviewer makes the
 *   "compile and push to live" decision.
 *
 * What the reviewer can do here:
 *   1. See how many saved test patients exercise this rule (counts
 *      both EXPECTED_RESULT-linked guideline patients AND
 *      ExpectedSBAR.matched_rule_ids-linked SBAR patients).
 *   2. Replay the unsaved draft against them in a sandbox.
 *   3. Author a brand-new patient against this rule with AI.
 *   4. Jump to the central library pre-filtered to this rule for
 *      bulk edits / deletes.
 *
 * Design controls: UN-50102672, DI-7625C251, DO-EE2C2EA1, R-8C0CC94B,
 * VT-5BDFE5F7. Phase 1 safety fix: DI-DD86CCBE, VT-D7B8FBA9 (see
 * Atlas).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import LaunchOutlinedIcon from "@mui/icons-material/LaunchOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";

import {
  listTestPatients,
  sandboxReplay,
} from "../../knowledge/test-patients/api";
import type {
  ReplayReport,
  TestPatientRow,
} from "../../knowledge/test-patients/types";
import ScaffoldFromRuleDialog from "../../knowledge/test-patients/ScaffoldFromRuleDialog";
import ReplayResultsDialog, {
  type RuleContext,
} from "../../knowledge/test-patients/replay/ReplayResultsDialog";
import { SANDBOX_AUTORUN, SANDBOX_PANEL } from "./copy";

/** Debounce window between the last draft edit and the auto-run
 *  sandbox replay. 1.5s lines up with the wizard's perception of an
 *  "edit pause" -- short enough that the reviewer feels the loop is
 *  fast, long enough that a multi-keystroke edit only fires once. */
const AUTORUN_DEBOUNCE_MS = 1500;

/**
 * Stable string signature of the draft rule. Used as the dependency
 * for the auto-run debounce so semantically identical drafts (object
 * identity changes but JSON shape unchanged) do not trigger an
 * unnecessary sandbox compile.
 */
function draftSignature(draft: Record<string, unknown> | null | undefined): string {
  if (!draft) return "";
  try {
    return JSON.stringify(draft);
  } catch {
    return "";
  }
}

/**
 * How many of the saved test patients fired the draft rule in this
 * sandbox replay. We treat any pass row whose ``rule_id`` matches
 * (or whose ``matched_as`` matches) as a fire so a re-saved rule
 * with a new id is not reported as 0/N.
 */
function countFiringPatients(
  report: ReplayReport,
  ruleId: string,
): number {
  let count = 0;
  for (const result of report.results) {
    const fired = result.passes.some((p) => {
      if (!p.fires) return false;
      return p.rule_id === ruleId || p.matched_as === ruleId;
    });
    if (fired) count += 1;
  }
  return count;
}

interface Props {
  /**
   * The saved (predecessor) rule id used to look up which test
   * patients exercise this rule. May be empty for a brand-new draft
   * that has never been saved -- in that case we render the
   * "save once before testing" empty state.
   */
  ruleId: string;
  guidelineId?: string;
  /** Plain English name of the rule, used to label regressions in
   *  the Replay results dialog. */
  ruleName?: string;
  /** Recommendation text the rule would have triggered, used to
   *  remind the reviewer what they will lose if it stops matching. */
  recommendationText?: string;
  /**
   * Snapshot of the rule the reviewer is currently editing. When set,
   * the panel offers a "Run sandbox test" button that compiles
   * ``draftRule`` into a sandbox bitmap and replays the saved
   * patients through it -- so the reviewer sees the impact of
   * unsaved edits BEFORE saving.
   */
  draftRule?: Record<string, unknown> | null;
  /**
   * Phase 4 wiring -- pushes the latest sandbox replay summary up
   * to the parent so the SentenceCanvas can render an inline
   * fire/no-fire badge per card. Called with ``null`` whenever the
   * draft signature changes (the previous report is stale) so the
   * parent never shows badges that disagree with the current draft.
   */
  onReportChange?: (
    state: SandboxReportState | null,
  ) => void;
}

/** Lightweight summary of the most recent sandbox run, surfaced to
 *  ancestors so they can render inline impact badges next to the
 *  sentence cards. The full ReplayReport is intentionally NOT
 *  exposed so consumers cannot accidentally render per-patient
 *  details outside the curated panel. */
export interface SandboxReportState {
  /** Status of the run that produced ``firingPatients``/``totalPatients``. */
  status: "fresh" | "stale" | "running" | "empty";
  firingPatients: number;
  totalPatients: number;
  /** Signature of the draft the badge corresponds to (for stale checks). */
  signature: string;
}

export default function TestPatientsPanel({
  ruleId,
  guidelineId,
  ruleName,
  recommendationText,
  draftRule,
  onReportChange,
}: Props) {
  const router = useRouter();

  const [patients, setPatients] = useState<TestPatientRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [sandboxRunning, setSandboxRunning] = useState(false);
  const [scaffoldOpen, setScaffoldOpen] = useState(false);
  const [openReplay, setOpenReplay] = useState(false);
  const [report, setReport] = useState<ReplayReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [sandboxNotCompiled, setSandboxNotCompiled] = useState(false);
  const [compileSummary, setCompileSummary] = useState<
    import("../../knowledge/test-patients/types").SandboxCompileSummary | null
  >(null);
  const [autoRun, setAutoRun] = useState(true);
  /** Signature of the draft the most recent ``report`` was produced
   *  against. When the live signature drifts away from this we know
   *  the report is stale and the badge must say so. */
  const [reportSignature, setReportSignature] = useState<string>("");
  const [autoRunPending, setAutoRunPending] = useState(false);

  const liveSignature = useMemo(() => draftSignature(draftRule), [draftRule]);

  const fetchPatients = useCallback(() => {
    if (!ruleId) {
      setPatients([]);
      return;
    }
    setLoading(true);
    setError(null);
    listTestPatients({ rule_id: ruleId, aspect: "all" })
      .then(setPatients)
      .catch(() => setError("Could not load saved patients."))
      .finally(() => setLoading(false));
  }, [ruleId]);

  useEffect(() => {
    fetchPatients();
  }, [fetchPatients, refreshKey]);

  const runSandboxReplay = useCallback(
    async (signatureAtCallTime: string) => {
      if (!draftRule || patients.length === 0) return null;
      setSandboxRunning(true);
      setError(null);
      setSandboxNotCompiled(false);
      setCompileSummary(null);
      try {
        const result = await sandboxReplay({
          rules: [draftRule],
          patient_ids: patients.map((p) => p.id),
          guideline_id: guidelineId,
        });
        setReport(result.report);
        setReportSignature(signatureAtCallTime);
        setCompileSummary(result.compile);
        const compiledZero = result.compile.rule_count === 0;
        setSandboxNotCompiled(compiledZero);
        return result.report;
      } catch (exc) {
        setError(
          exc instanceof Error
            ? exc.message
            : "Could not test the draft against the library.",
        );
        return null;
      } finally {
        setSandboxRunning(false);
      }
    },
    [draftRule, patients, guidelineId],
  );

  /**
   * Phase 4 -- debounced auto-run on commit. After the draft tree
   * stops changing for ``AUTORUN_DEBOUNCE_MS`` we re-run the
   * sandbox so the inline impact badges stay fresh. The reviewer
   * can opt out with the checkbox below; either way the explicit
   * "Run now" button always works.
   */
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (
      !autoRun ||
      !draftRule ||
      patients.length === 0 ||
      !liveSignature ||
      liveSignature === reportSignature
    ) {
      setAutoRunPending(false);
      return;
    }
    setAutoRunPending(true);
    const sigAtSchedule = liveSignature;
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      setAutoRunPending(false);
      void runSandboxReplay(sigAtSchedule);
    }, AUTORUN_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [
    autoRun,
    draftRule,
    patients.length,
    liveSignature,
    reportSignature,
    runSandboxReplay,
  ]);

  /**
   * Phase 4 -- push the badge state up to the parent (EditRuleDialog
   * -> Step1Who -> SentenceCanvas) on every state change. The badge
   * is "fresh" only when the report's signature still matches the
   * live draft; otherwise it is "stale" so the canvas can prompt the
   * reviewer to re-run.
   */
  useEffect(() => {
    if (!onReportChange) return;
    const total = patients.length;
    if (sandboxRunning) {
      onReportChange({
        status: "running",
        firingPatients: 0,
        totalPatients: total,
        signature: liveSignature,
      });
      return;
    }
    if (!report || !ruleId) {
      onReportChange({
        status: "empty",
        firingPatients: 0,
        totalPatients: total,
        signature: liveSignature,
      });
      return;
    }
    const firing = countFiringPatients(report, ruleId);
    const stale =
      reportSignature !== "" && reportSignature !== liveSignature;
    onReportChange({
      status: stale ? "stale" : "fresh",
      firingPatients: firing,
      totalPatients: total,
      signature: reportSignature,
    });
  }, [
    onReportChange,
    report,
    sandboxRunning,
    reportSignature,
    liveSignature,
    patients.length,
    ruleId,
  ]);

  const regressionCount = report?.regressions_count ?? 0;
  const passCount = report?.passes_count ?? 0;

  const ruleLookup = useMemo<Record<string, RuleContext>>(
    () => ({
      [ruleId]: {
        name: ruleName,
        recommendation_text: recommendationText,
      },
    }),
    [ruleId, ruleName, recommendationText],
  );

  const openInLibrary = useCallback(() => {
    const qs = new URLSearchParams({
      tab: "test-patients",
      ...(ruleId ? { rule_id: ruleId } : {}),
    });
    router.push(`/admin/knowledge?${qs.toString()}`);
  }, [router, ruleId]);

  // Empty-state: brand-new rule that has never been saved. There is
  // no rule_id to attach test patients to, and "saving once" is
  // currently the only path to attach them.
  if (!ruleId) {
    return (
      <Box
        sx={{
          p: 1.5,
          borderRadius: 1,
          bgcolor: "grey.50",
          border: "1px solid",
          borderColor: "grey.200",
        }}
        role="status"
        aria-label={SANDBOX_PANEL.ruleNotSavedTitle}
      >
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {SANDBOX_PANEL.ruleNotSavedTitle}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {SANDBOX_PANEL.ruleNotSavedBody}
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 1,
        bgcolor: "grey.50",
        border: "1px solid",
        borderColor: "grey.200",
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          {SANDBOX_PANEL.heading}
        </Typography>
        <Chip
          size="small"
          label={`${patients.length} saved`}
          color={patients.length > 0 ? "primary" : "default"}
          variant="outlined"
        />
        {report && (
          <>
            <Chip
              size="small"
              color={regressionCount === 0 ? "success" : "error"}
              label={`${regressionCount} regress`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`${passCount} pass`}
            />
          </>
        )}
      </Stack>

      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 0.5 }}
      >
        {SANDBOX_PANEL.intro}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 1 }} role="status">
          {error}
        </Alert>
      )}

      {sandboxNotCompiled && (
        <Alert severity="warning" sx={{ mt: 1 }} role="status">
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            {SANDBOX_PANEL.compileFailedTitle}
          </Typography>
          {SANDBOX_PANEL.compileFailedBody}
          {compileSummary && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.75 }}
            >
              Compile stats: {compileSummary.rule_count} of{" "}
              {compileSummary.draft_input_count} rule
              {compileSummary.draft_input_count === 1 ? "" : "s"} included.
              {compileSummary.compile_stats?.rules_excluded
                ? ` ${compileSummary.compile_stats.rules_excluded} excluded.`
                : ""}
            </Typography>
          )}
        </Alert>
      )}

      {compileSummary &&
        !sandboxNotCompiled &&
        compileSummary.rule_count < compileSummary.draft_input_count && (
          <Alert severity="warning" sx={{ mt: 1 }} role="status">
            {SANDBOX_PANEL.compilePartialBody(
              compileSummary.rule_count,
              compileSummary.draft_input_count,
            )}
          </Alert>
        )}

      {report && regressionCount > 0 && (
        <Alert
          severity="error"
          sx={{ mt: 1 }}
          role="status"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => setOpenReplay(true)}
            >
              View report
            </Button>
          }
        >
          {regressionCount} test patient assertion
          {regressionCount === 1 ? "" : "s"} no longer match
          {regressionCount === 1 ? "es" : ""} this rule in the sandbox.
          Open the report to see which patient
          {regressionCount === 1 ? "" : "s"} stopped matching.
        </Alert>
      )}

      <Stack
        direction="row"
        spacing={1}
        sx={{ mt: 1, flexWrap: "wrap", rowGap: 1 }}
      >
        <Button
          size="small"
          variant="contained"
          color="primary"
          startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />}
          onClick={() => setScaffoldOpen(true)}
          aria-label="Author a new test patient with AI, locked to this rule"
        >
          Author with AI from this rule
        </Button>
        <Button
          size="small"
          variant="outlined"
          startIcon={<LaunchOutlinedIcon fontSize="small" />}
          onClick={openInLibrary}
          aria-label="Open the central Test Patient library filtered by this rule"
        >
          Open in Test Patient Library
        </Button>
        {loading && <CircularProgress size={16} />}
      </Stack>

      {patients.length === 0 && !loading && (
        <Box
          sx={{
            mt: 1.5,
            p: 1.25,
            borderRadius: 1,
            bgcolor: "background.paper",
            border: "1px dashed",
            borderColor: "grey.300",
          }}
          role="status"
          aria-label={SANDBOX_PANEL.noPatientsTitle}
        >
          <Typography variant="subtitle2" sx={{ mb: 0.25 }}>
            {SANDBOX_PANEL.noPatientsTitle}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 1, lineHeight: 1.5 }}
          >
            {SANDBOX_PANEL.noPatientsBody}
          </Typography>
          <Button
            size="small"
            variant="contained"
            color="primary"
            startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />}
            onClick={() => setScaffoldOpen(true)}
            aria-label="Add the first test patient by authoring one with AI from this rule"
          >
            Add a test patient
          </Button>
        </Box>
      )}

      {patients.length > 0 && !draftRule && (
        <Box
          sx={{
            mt: 1.5,
            p: 1.25,
            borderRadius: 1,
            bgcolor: "background.paper",
            border: "1px dashed",
            borderColor: "grey.300",
          }}
          role="status"
        >
          <Typography variant="subtitle2" sx={{ mb: 0.25 }}>
            {SANDBOX_PANEL.noDraftYetTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {SANDBOX_PANEL.noDraftYetBody}
          </Typography>
        </Box>
      )}

      {draftRule && patients.length > 0 && (
        <Box
          sx={{
            mt: 1.5,
            p: 1.25,
            borderRadius: 1,
            bgcolor: "primary.50",
            border: "1px dashed",
            borderColor: "primary.200",
          }}
        >
          <Stack direction="row" spacing={0.75} alignItems="center">
            <ScienceOutlinedIcon fontSize="small" color="primary" />
            <Typography variant="subtitle2" sx={{ flex: 1 }}>
              {SANDBOX_PANEL.draftCardTitle}
            </Typography>
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label="Sandbox"
            />
          </Stack>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.25 }}
          >
            {SANDBOX_PANEL.draftCardCaption}
          </Typography>
          <Stack
            direction="row"
            spacing={1}
            sx={{ mt: 0.75, alignItems: "center", flexWrap: "wrap", rowGap: 0.5 }}
          >
            <Button
              size="small"
              variant="contained"
              color="primary"
              disabled={sandboxRunning}
              onClick={() => {
                runSandboxReplay(liveSignature).then((r) => {
                  if (r) setOpenReplay(true);
                });
              }}
              startIcon={
                sandboxRunning ? (
                  <CircularProgress size={14} color="inherit" />
                ) : (
                  <ScienceOutlinedIcon fontSize="small" />
                )
              }
              aria-label="Test the unsaved draft against the saved test patients in a sandbox"
            >
              {sandboxRunning
                ? SANDBOX_PANEL.testButtonRunning
                : SANDBOX_PANEL.testButton}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="primary"
              disabled={sandboxRunning}
              onClick={() => {
                void runSandboxReplay(liveSignature);
              }}
              aria-label={
                sandboxRunning
                  ? SANDBOX_AUTORUN.runNowRunningAria
                  : SANDBOX_AUTORUN.runNowAria
              }
            >
              {SANDBOX_AUTORUN.runNowLabel}
            </Button>
            <Tooltip title={SANDBOX_AUTORUN.toggleHint}>
              <FormControlLabel
                sx={{ ml: 0.5, mr: 0 }}
                control={
                  <Checkbox
                    size="small"
                    checked={autoRun}
                    onChange={(_e, checked) => setAutoRun(checked)}
                    inputProps={{
                      "aria-label": SANDBOX_AUTORUN.toggleLabel,
                    }}
                  />
                }
                label={
                  <Typography variant="caption" color="text.secondary">
                    {SANDBOX_AUTORUN.toggleLabel}
                  </Typography>
                }
              />
            </Tooltip>
            {autoRunPending && (
              <Chip
                size="small"
                color="info"
                variant="outlined"
                label={SANDBOX_AUTORUN.pendingDebounceLabel}
                sx={{ height: 22, fontSize: "0.7rem" }}
              />
            )}
          </Stack>
          {!autoRun &&
            reportSignature !== "" &&
            reportSignature !== liveSignature &&
            !sandboxRunning && (
              <Typography
                variant="caption"
                color="warning.dark"
                sx={{ display: "block", mt: 0.5, lineHeight: 1.4 }}
              >
                {SANDBOX_AUTORUN.staleNotice}
              </Typography>
            )}
        </Box>
      )}

      <ScaffoldFromRuleDialog
        open={scaffoldOpen}
        initialAspect="summarisation"
        lockedRuleId={ruleId}
        lockedRuleHint={ruleName}
        draftRule={draftRule}
        onClose={() => setScaffoldOpen(false)}
        onScaffolded={() => {
          setScaffoldOpen(false);
          setRefreshKey((n) => n + 1);
        }}
      />

      <ReplayResultsDialog
        open={openReplay}
        onClose={() => setOpenReplay(false)}
        report={report}
        patients={patients}
        rules={ruleLookup}
        mode="sandbox"
        scopeType={report?.scope_type ?? compileSummary?.scope_type}
        scopeId={report?.scope_id ?? compileSummary?.scope_id}
      />
    </Box>
  );
}
