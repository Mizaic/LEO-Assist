"use client";

/**
 * Compact "Test patients" panel embedded in the EditRuleDialog.
 *
 * Shows how many saved test patients target this rule, lets the
 * reviewer launch the Build / Generate dialogs scoped to this rule,
 * and runs an on-demand replay against the rule so they can spot
 * regressions caused by their edits.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";

import BuildPatientDialog from "../test-patients/BuildPatientDialog";
import GeneratePatientsDialog from "../test-patients/GeneratePatientsDialog";
import ReplayResultsDialog from "../test-patients/ReplayResultsDialog";
import RulesetNotCompiledBanner from "../test-patients/RulesetNotCompiledBanner";
import type { RuleContext } from "../test-patients/ReplayResultsDialog";
import {
  getBitmapStatus,
  listPatients,
  replay,
  sandboxReplay,
} from "../test-patients/api";
import type { ReplayReport, TestPatient } from "../test-patients/types";

interface Props {
  ruleId: string;
  guidelineId?: string;
  /**
   * Bumped by the parent every time the rule's logic changes, so we
   * auto-rerun the replay and show the latest banner.
   */
  ruleSignature?: string;
  /** Plain English name of the rule, used to label regressions in
   *  the Replay results dialog. */
  ruleName?: string;
  /** Recommendation text the rule would have triggered, used to
   *  remind the reviewer what they will lose if it stops matching. */
  recommendationText?: string;
  /**
   * Snapshot of the rule the reviewer is currently editing. When set,
   * the panel offers a "Test draft against library" button that
   * compiles ``draftRule`` into a sandbox bitmap and replays the
   * saved patients through it -- so the reviewer sees the impact of
   * unsaved edits BEFORE saving.
   */
  draftRule?: Record<string, unknown> | null;
}

export default function TestPatientsPanel({
  ruleId,
  guidelineId,
  ruleSignature,
  ruleName,
  recommendationText,
  draftRule,
}: Props) {
  const [patients, setPatients] = useState<TestPatient[]>([]);
  const [loading, setLoading] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [sandboxRunning, setSandboxRunning] = useState(false);
  const [openBuild, setOpenBuild] = useState(false);
  const [openGenerate, setOpenGenerate] = useState(false);
  const [openReplay, setOpenReplay] = useState(false);
  const [report, setReport] = useState<ReplayReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notCompiled, setNotCompiled] = useState(false);
  const [scope, setScope] = useState<{ type: string; id: string }>({
    type: guidelineId ? "guideline" : "global",
    id: guidelineId || "default",
  });
  const [reportSandbox, setReportSandbox] = useState(false);

  const fetchPatients = useCallback(() => {
    if (!ruleId) return;
    setLoading(true);
    setError(null);
    listPatients({ rule_id: ruleId })
      .then(setPatients)
      .catch(() => setError("Could not load saved patients."))
      .finally(() => setLoading(false));
  }, [ruleId]);

  useEffect(() => {
    fetchPatients();
  }, [fetchPatients, refreshKey]);

  const runReplay = useCallback(async () => {
    if (patients.length === 0) return null;
    setReplaying(true);
    setError(null);
    setNotCompiled(false);
    setReportSandbox(false);
    const liveScope = {
      type: guidelineId ? "guideline" : "global",
      id: guidelineId || "default",
    };
    setScope(liveScope);
    try {
      const result = await replay({
        patient_ids: patients.map((p) => p.id),
        scope_type: liveScope.type,
        scope_id: liveScope.id,
        persist_report: false,
      });
      setReport(result);
      // Detect "no ruleset" by looking for the per-patient error
      // string the evaluator surfaces. Every patient hit the same
      // missing scope, so a single match is enough.
      const looksUncompiled = (result.results || []).some((row) =>
        (row.error || "").toLowerCase().includes("no active ruleset"),
      );
      setNotCompiled(looksUncompiled);
      return result;
    } catch (exc) {
      const msg =
        exc instanceof Error ? exc.message : "Could not replay the patients.";
      if (msg.toLowerCase().includes("no active ruleset")) {
        setNotCompiled(true);
      } else {
        setError(msg);
      }
      return null;
    } finally {
      setReplaying(false);
    }
  }, [patients, guidelineId]);

  const runSandboxReplay = useCallback(async () => {
    if (!draftRule || patients.length === 0) return null;
    setSandboxRunning(true);
    setError(null);
    setNotCompiled(false);
    try {
      const result = await sandboxReplay({
        rules: [draftRule],
        patient_ids: patients.map((p) => p.id),
        guideline_id: guidelineId,
      });
      const sandboxScope = {
        type: result.compile.scope_type,
        id: result.compile.scope_id,
      };
      setScope(sandboxScope);
      setReportSandbox(true);
      setReport(result.report);
      const compiledZero = result.compile.rule_count === 0;
      setNotCompiled(compiledZero);
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
  }, [draftRule, patients, guidelineId]);

  const checkCompiledStatus = useCallback(async () => {
    try {
      const status = await getBitmapStatus(
        guidelineId ? "guideline" : "global",
        guidelineId || "default",
      );
      setNotCompiled(!status.active_version || status.rule_count === 0);
    } catch {
      // Best-effort: if status is unreachable, the replay-error path
      // below still surfaces the missing ruleset.
    }
  }, [guidelineId]);

  useEffect(() => {
    checkCompiledStatus();
  }, [checkCompiledStatus, refreshKey]);

  // Auto-replay whenever the rule signature changes -- the parent flips
  // this on every logic-tree edit so the banner is always fresh.
  useEffect(() => {
    if (!ruleSignature || patients.length === 0) return;
    runReplay();
  }, [ruleSignature, patients.length, runReplay]);

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
          Test patients for this rule
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

      <Typography variant="caption" color="text.secondary">
        Patients here run automatically every time you save changes, so you
        spot any rule that quietly stops matching the way it should.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 1 }} role="status">
          {error}
        </Alert>
      )}

      {notCompiled && (
        <RulesetNotCompiledBanner
          scopeType={scope.type}
          scopeId={scope.id}
          sandbox={reportSandbox}
          onCompileRequested={() => {
            // Re-check status periodically -- the compile is async.
            // The reviewer can also click "Replay now" once the
            // bitmap finishes building.
            setTimeout(() => {
              checkCompiledStatus();
            }, 4000);
          }}
        />
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
          {regressionCount === 1 ? "es" : ""} this rule against the
          {reportSandbox ? " sandbox / unsaved draft" : " live ruleset"}.
          Open the report to see which patient
          {regressionCount === 1 ? "" : "s"} stopped matching.
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        <Button
          size="small"
          variant="outlined"
          onClick={() => setOpenBuild(true)}
          disabled={!guidelineId}
        >
          Build new
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={() => setOpenGenerate(true)}
        >
          Generate
        </Button>
        {loading && <CircularProgress size={16} />}
      </Stack>

      <Divider sx={{ mt: 1.5, mb: 1 }} />

      <Box
        sx={{
          p: 1,
          borderRadius: 1,
          bgcolor: "success.50",
          border: "1px solid",
          borderColor: "success.100",
        }}
      >
        <Stack direction="row" spacing={0.75} alignItems="center">
          <PlayCircleOutlineIcon fontSize="small" color="success" />
          <Typography variant="subtitle2" sx={{ flex: 1 }}>
            Test against the live ruleset
          </Typography>
          <Chip
            size="small"
            color="success"
            variant="outlined"
            label="Live"
          />
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.25 }}
        >
          Runs the saved patients against the rule that is already deployed
          in production (the bitmap currently in Redis). Use this to confirm
          the SAVED rule still behaves the way you expect.
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 0.75 }}>
          <Button
            size="small"
            variant="contained"
            color="success"
            disabled={replaying || patients.length === 0}
            onClick={() => {
              runReplay().then((r) => {
                if (r) setOpenReplay(true);
              });
            }}
            startIcon={
              replaying ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <PlayCircleOutlineIcon fontSize="small" />
              )
            }
            aria-label="Test the saved rule against the production ruleset"
          >
            {replaying ? "Testing live..." : "Test against live"}
          </Button>
        </Stack>
      </Box>

      {draftRule && (
        <Box
          sx={{
            mt: 1,
            p: 1,
            borderRadius: 1,
            bgcolor: "primary.50",
            border: "1px dashed",
            borderColor: "primary.200",
          }}
        >
          <Stack direction="row" spacing={0.75} alignItems="center">
            <ScienceOutlinedIcon fontSize="small" color="primary" />
            <Typography variant="subtitle2" sx={{ flex: 1 }}>
              Test your unsaved draft (sandbox)
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
            Compiles the rule you are editing right now into a throwaway
            bitmap, runs the saved patients against it, and discards the
            sandbox. Production is NOT touched. Use this to see how a
            pending edit would behave BEFORE saving.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.75 }}>
            <Button
              size="small"
              variant="contained"
              color="primary"
              disabled={sandboxRunning || patients.length === 0}
              onClick={() => {
                runSandboxReplay().then((r) => {
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
              {sandboxRunning ? "Testing draft..." : "Test draft in sandbox"}
            </Button>
          </Stack>
        </Box>
      )}

      {openBuild && guidelineId && (
        <BuildPatientDialog
          open={openBuild}
          onClose={() => setOpenBuild(false)}
          guidelineId={guidelineId}
          onSaved={() => {
            setOpenBuild(false);
            setRefreshKey((n) => n + 1);
          }}
        />
      )}

      <GeneratePatientsDialog
        open={openGenerate}
        onClose={() => setOpenGenerate(false)}
        guidelineId={guidelineId}
        ruleId={ruleId}
        onSaved={(count) => {
          if (count > 0) setRefreshKey((n) => n + 1);
        }}
      />

      <ReplayResultsDialog
        open={openReplay}
        onClose={() => setOpenReplay(false)}
        report={report}
        patients={patients}
        rules={ruleLookup}
        mode={reportSandbox ? "sandbox" : "live"}
      />
    </Box>
  );
}
