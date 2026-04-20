/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Compact "Try it on real patients" panel embedded in the
 * EditRuleDialog.
 *
 * This is the rule editor's view onto the centralised Test Patient
 * library (Knowledge > Test Patients). It does NOT own its own data
 * model -- all reads and writes go through the central api.ts under
 *   services/ui/src/app/admin/knowledge/test-patients/
 *
 * What the reviewer can do here:
 *   1. See how many saved test patients exercise this rule (counts
 *      both EXPECTED_RESULT-linked guideline patients AND
 *      ExpectedSBAR.matched_rule_ids-linked SBAR patients).
 *   2. Replay them against the live (production) ruleset.
 *   3. Replay them against the unsaved draft in a throwaway sandbox.
 *   4. Author a brand-new patient against this rule with AI -- opens
 *      the central ScaffoldFromRuleDialog with the rule pre-selected
 *      and locked.
 *   5. Jump to the central library pre-filtered to this rule for
 *      bulk edits / deletes.
 *
 * Design controls: UN-50102672, DI-7625C251, DO-EE2C2EA1, R-8C0CC94B,
 * VT-5BDFE5F7. The legacy /admin/guidance/test-patients folder is
 * removed in this same change set.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import LaunchOutlinedIcon from "@mui/icons-material/LaunchOutlined";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";

import {
  getBitmapStatus,
  listTestPatients,
  replay,
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
import RulesetNotCompiledBanner from "../../knowledge/test-patients/replay/RulesetNotCompiledBanner";

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
  const router = useRouter();

  const [patients, setPatients] = useState<TestPatientRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [sandboxRunning, setSandboxRunning] = useState(false);
  const [scaffoldOpen, setScaffoldOpen] = useState(false);
  const [openReplay, setOpenReplay] = useState(false);
  const [report, setReport] = useState<ReplayReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notCompiled, setNotCompiled] = useState(false);
  // The platform compiles a single production bitmap at scope_type=
  // "global" / scope_id="default" that holds rules for every guideline.
  // Per-guideline scopes are only used by sandbox / draft compiles, so
  // probing scope_type="guideline" gave false "no ruleset" warnings
  // even when the global bitmap was loaded and contained the rule.
  // We always check status + replay against global, then pass
  // guideline_id through to scope the evaluation to just this
  // guideline (the backend treats guideline_id as a pathway_filter).
  const [scope, setScope] = useState<{ type: string; id: string }>({
    type: "global",
    id: "default",
  });
  const [reportSandbox, setReportSandbox] = useState(false);

  const fetchPatients = useCallback(() => {
    if (!ruleId) return;
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

  const runReplay = useCallback(async () => {
    if (patients.length === 0) return null;
    setReplaying(true);
    setError(null);
    setNotCompiled(false);
    setReportSandbox(false);
    const liveScope = { type: "global", id: "default" };
    setScope(liveScope);
    try {
      const result = await replay({
        patient_ids: patients.map((p) => p.id),
        scope_type: liveScope.type,
        scope_id: liveScope.id,
        guideline_id: guidelineId,
        persist_report: false,
      });
      setReport(result);
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
      const status = await getBitmapStatus("global", "default");
      setNotCompiled(!status.active_version || status.rule_count === 0);
    } catch {
      // Best-effort: if status is unreachable, the replay-error path
      // below still surfaces the missing ruleset.
    }
  }, []);

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

  const openInLibrary = useCallback(() => {
    const qs = new URLSearchParams({
      tab: "test-patients",
      rule_id: ruleId,
    });
    router.push(`/admin/knowledge?${qs.toString()}`);
  }, [router, ruleId]);

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
          Try it on real patients
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
        Patients here run automatically every time you save changes, so
        you spot any rule that quietly stops matching the way it
        should. They live in the central Test Patient library.
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
          Runs the saved patients against the rule that is already
          deployed in production (the bitmap currently in Redis). Use
          this to confirm the SAVED rule still behaves the way you
          expect.
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
            Compiles the rule you are editing right now into a
            throwaway bitmap, runs the saved patients against it, and
            discards the sandbox. Production is NOT touched. Use this
            to see how a pending edit would behave BEFORE saving.
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

      <ScaffoldFromRuleDialog
        open={scaffoldOpen}
        initialAspect="summarisation"
        lockedRuleId={ruleId}
        lockedRuleHint={ruleName}
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
        mode={reportSandbox ? "sandbox" : "live"}
      />
    </Box>
  );
}
