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
 * ReplayResultsDialog -- ISO 13485 / IEC 62304 style test report
 * presentation for a guideline-rule replay run.
 *
 * The visible copy is written for a UK reading age of 11 (see
 * .cursor/rules/health-literacy.mdc) so a clinical safety officer or
 * QA reviewer who is not a rules engineer can sign the report off.
 * Internal terms ("bitmap", "regression", "drift", "ruleset") are
 * deliberately translated at the boundary -- they remain in the
 * underlying API contracts (ReplayReport, DiagnoseResponse) but the
 * UI shows: passed / failed / changed since saved / set of rules /
 * matches.
 *
 * Report layout, top to bottom:
 *
 *   1. Header        -- title, live-vs-sandbox chip, one-line summary
 *   2. Verdict       -- big green PASSED or red FAILED banner
 *   3. What we tested -- facts row (rules version, source, patient
 *                       count, check count, scope) -- this is the
 *                       "configuration under test" section a 13485
 *                       auditor expects on every test report
 *   4. Results       -- one accordion row per patient with the
 *                       per-rule "expected / found" detail and the
 *                       annotated tree from the same evaluator that
 *                       production uses
 *   5. Audit footer  -- provenance line: which engine produced this
 *                       report, which rules version, when
 *
 * Each result row is expandable. When the row contains a failed
 * check we call ``/api/guidance/test-patients/diagnose`` -- which is
 * backed by the SAME roaring-bitmap evaluator that production uses
 * to fire rules -- so the per-part diagnostic is guaranteed to agree
 * with the live decision. The annotated tree is rendered
 * hierarchically (preserving AND / OR / NOT / AT_LEAST grouping) so
 * the reviewer can see exactly which part of the rule did or did
 * not match.
 *
 * Lives under the central Knowledge > Test Patients library so the
 * rule editor and central library can share one dialog. Uses the
 * lightweight ReplayPatientSummary shape so callers can pass either
 * a TestPatientRow or a richer snapshot.
 */

import { useEffect, useMemo, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import RulesetNotCompiledBanner from "./RulesetNotCompiledBanner";
import { diagnose } from "../api";
import type {
  DiagnoseNode,
  DiagnoseResponse,
  ReplayPatientResult,
  ReplayPatientSummary,
  ReplayReport,
} from "../types";

/** Minimal rule context the dialog needs to label a regression heading. */
export interface RuleContext {
  name?: string;
  recommendation_text?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  report: ReplayReport | null;
  /** Saved patients in scope, used to render the patient summary. */
  patients?: ReplayPatientSummary[];
  /** Optional rule lookup keyed by rule_id, used for friendly headings. */
  rules?: Record<string, RuleContext>;
  /** Scope passed to the diagnose endpoint (defaults to global/default). */
  scopeType?: string;
  scopeId?: string;
  /**
   * Whether the report came from the live production ruleset or a
   * throwaway sandbox compile of an unsaved draft. Drives the title
   * and a coloured chip so reviewers cannot mistake a sandbox result
   * for a live one (or vice versa).
   */
  mode?: "live" | "sandbox";
}

export default function ReplayResultsDialog({
  open,
  onClose,
  report,
  patients,
  rules,
  scopeType,
  scopeId,
  mode = "live",
}: Props) {
  const patientsById = useMemo(() => {
    const map: Record<string, ReplayPatientSummary> = {};
    (patients ?? []).forEach((p) => {
      map[p.id] = p;
    });
    return map;
  }, [patients]);

  const isSandbox = mode === "sandbox";
  const rulesetMissing = report ? reportRulesetMissing(report) : false;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ flex: 1 }}>
            {isSandbox
              ? "Test report -- unsaved draft (sandbox)"
              : "Test report -- live rules"}
          </Box>
          <Chip
            size="small"
            color={isSandbox ? "primary" : "success"}
            variant={isSandbox ? "outlined" : "filled"}
            label={isSandbox ? "Sandbox" : "Live"}
          />
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.25 }}
        >
          {isSandbox
            ? "We checked your saved patients against the rule you are editing. The live rules were NOT touched."
            : "We checked your saved patients against the set of rules that is live in production right now."}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        {!report ? (
          <Typography variant="body2" color="text.secondary">
            Run a test to see results here.
          </Typography>
        ) : (
          <Stack spacing={2}>
            <VerdictBanner
              report={report}
              rulesetMissing={rulesetMissing}
            />

            {rulesetMissing && (
              <RulesetNotCompiledBanner
                scopeType={report.scope_type}
                scopeId={report.scope_id}
                detail={
                  "We could not load the live rules for this scope. " +
                  "That means every rule looks like it 'did not match' " +
                  "to the engine. Patients you saved as 'should match' " +
                  "will show as failed, and patients you saved as " +
                  "'should NOT match' will show as passed by accident. " +
                  "Please rebuild the rules and run this test again " +
                  "before you trust the result."
                }
              />
            )}

            <WhatWasTested
              report={report}
              isSandbox={isSandbox}
              rulesetMissing={rulesetMissing}
            />

            <Box>
              <Typography variant="subtitle2">Results, by patient</Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 1 }}
              >
                One row per patient. Click a row to see the patient and
                which parts of the rule did or did not match.
              </Typography>
              <Stack spacing={1}>
                {report.results.map((row) => (
                  <PatientResultRow
                    key={row.patient_id}
                    row={row}
                    patient={patientsById[row.patient_id]}
                    rules={rules}
                    scopeType={scopeType}
                    scopeId={scopeId}
                    rulesetVersion={report.ruleset_version}
                    rulesetMissing={rulesetMissing}
                  />
                ))}
              </Stack>
            </Box>

            <AuditFooter report={report} isSandbox={isSandbox} />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

function reportRulesetMissing(report: ReplayReport): boolean {
  if (!report.results || report.results.length === 0) return false;
  return report.results.every((row) =>
    (row.error || "").toLowerCase().includes("no active ruleset"),
  );
}

/**
 * Top-of-report verdict banner. ISO 13485 verification reports lead
 * with a single PASS / FAIL outcome so the auditor never has to
 * guess. We mirror that here: green PASSED, red FAILED, or amber
 * INCONCLUSIVE when no rules were loaded.
 */
function VerdictBanner({
  report,
  rulesetMissing,
}: {
  report: ReplayReport;
  rulesetMissing: boolean;
}) {
  if (rulesetMissing) {
    return (
      <Alert severity="warning" icon={false} sx={{ alignItems: "center" }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Inconclusive -- the rules are not loaded
        </Typography>
        <Typography variant="body2">
          We could not run the test because the rule engine has no
          rules loaded right now. Please rebuild the rules and try again.
        </Typography>
      </Alert>
    );
  }

  const passed = report.regressions_count === 0;
  const checks = report.passes_count + report.regressions_count;
  const checksWord = checks === 1 ? "check" : "checks";
  const failsWord = report.regressions_count === 1 ? "check" : "checks";

  if (passed) {
    return (
      <Alert
        severity="success"
        icon={<CheckCircleOutlineIcon />}
        sx={{ alignItems: "center" }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Passed
        </Typography>
        <Typography variant="body2">
          {checks === 0
            ? "No saved checks to run yet. Add an expected outcome to a patient to start testing."
            : `All ${checks} saved ${checksWord} matched the rules. Nothing has broken since these patients were saved.`}
        </Typography>
      </Alert>
    );
  }

  return (
    <Alert
      severity="error"
      icon={<CancelOutlinedIcon />}
      sx={{ alignItems: "center" }}
    >
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Failed -- {report.regressions_count} saved {failsWord} no longer
        match the rules
      </Typography>
      <Typography variant="body2">
        Open the failed rows below to see which patient is affected
        and which part of the rule changed.
      </Typography>
    </Alert>
  );
}

/**
 * "What we tested" -- the configuration-under-test block. Shows the
 * rules version, where the rules came from, how many patients were
 * checked, how many checks were made, and the scope. This is the
 * minimum metadata an ISO 13485 / IEC 62304 verification report
 * needs to be reproducible.
 */
function WhatWasTested({
  report,
  isSandbox,
  rulesetMissing,
}: {
  report: ReplayReport;
  isSandbox: boolean;
  rulesetMissing: boolean;
}) {
  const totalChecks = report.passes_count + report.regressions_count;
  const facts: Array<{ label: string; value: string; hint?: string }> = [
    {
      label: "Source of rules",
      value: isSandbox
        ? "Throwaway draft (sandbox)"
        : "Live in production",
      hint: isSandbox
        ? "A copy of the rule you are editing. Your live rules were not changed."
        : "The same rules that decide real patient referrals right now.",
    },
    {
      label: "Rules version",
      value: report.ruleset_version || "(none loaded)",
      hint: "A version stamp set when the rules were last built.",
    },
    {
      label: "Patients tested",
      value: String(report.patient_count),
    },
    {
      label: "Checks made",
      value: String(totalChecks),
      hint:
        "Each saved patient can ask one or more questions of the rules " +
        "(for example, 'should match the mesothelioma rule'). " +
        "We counted every question.",
    },
    {
      label: "Scope",
      value: `${report.scope_type} / ${report.scope_id}`,
      hint: "Which set of rules we ran the test against.",
    },
  ];

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 1,
        border: "1px solid",
        borderColor: "grey.300",
        bgcolor: "grey.50",
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        What we tested
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          columnGap: 2,
          rowGap: 0.75,
        }}
      >
        {facts.map((fact) => (
          <Box key={fact.label}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", textTransform: "uppercase", fontSize: "0.65rem" }}
            >
              {fact.label}
            </Typography>
            <Tooltip title={fact.hint || ""} arrow disableHoverListener={!fact.hint}>
              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                {fact.value}
              </Typography>
            </Tooltip>
          </Box>
        ))}
      </Box>
      {!rulesetMissing && (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          sx={{ mt: 1.25 }}
        >
          <Chip
            size="small"
            color={report.regressions_count === 0 ? "success" : "error"}
            variant="filled"
            label={`${report.regressions_count} failed`}
          />
          <Chip
            size="small"
            color="success"
            variant="outlined"
            label={`${report.passes_count} passed`}
          />
          <Tooltip
            title={
              "A patient saved against an older version of a rule that has since " +
              "been edited. The test still passes because we match by the rule's " +
              "stable name, but the version stamp changed."
            }
            arrow
          >
            <Chip
              size="small"
              color={report.drift_count > 0 ? "warning" : "default"}
              variant="outlined"
              label={`${report.drift_count} changed since saved`}
            />
          </Tooltip>
        </Stack>
      )}
    </Box>
  );
}

/**
 * Audit-trail footer. ISO 13485 reports end with provenance: who or
 * what produced the result, what version of the system was tested,
 * and when. The web dialog cannot record a wet signature but it can
 * surface the same machine-checkable facts.
 */
function AuditFooter({
  report,
  isSandbox,
}: {
  report: ReplayReport;
  isSandbox: boolean;
}) {
  return (
    <Box sx={{ pt: 1, borderTop: "1px solid", borderColor: "grey.200" }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block" }}
      >
        This test was run by the same rule engine that decides real
        referrals.
        {isSandbox
          ? " It used a one-off copy of the rule you are editing, so your live rules were not changed."
          : " It used the live rules currently deployed to production."}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block" }}
      >
        Rules version:{" "}
        <Box component="span" sx={{ fontFamily: "monospace" }}>
          {report.ruleset_version || "(none)"}
        </Box>
        {" -- Generated just now"}
      </Typography>
    </Box>
  );
}

interface RowProps {
  row: ReplayPatientResult;
  patient?: ReplayPatientSummary;
  rules?: Record<string, RuleContext>;
  scopeType?: string;
  scopeId?: string;
  rulesetVersion: string | null;
  rulesetMissing?: boolean;
}

function PatientResultRow({
  row,
  patient,
  rules,
  scopeType,
  scopeId,
  rulesetVersion,
  rulesetMissing,
}: RowProps) {
  const isRegression = row.regressions.length > 0;
  const intent = computePatientIntent(row);
  return (
    <Accordion
      disableGutters
      square={false}
      sx={{
        borderRadius: 1,
        bgcolor: isRegression ? "error.50" : "grey.50",
        border: "1px solid",
        borderColor: isRegression ? "error.200" : "grey.200",
        "&:before": { display: "none" },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        aria-label={`Show details for ${row.patient_name || row.patient_id}`}
        sx={{ px: 1.5 }}
      >
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          sx={{ width: "100%" }}
        >
          <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
            {row.patient_name || row.patient_id}
          </Typography>
          <Tooltip title={intent.tooltip} arrow>
            <Chip
              size="small"
              color={intent.color}
              variant="outlined"
              label={intent.label}
              aria-label={intent.tooltip}
            />
          </Tooltip>
          <Chip
            size="small"
            color={rulesetMissing ? "default" : "success"}
            variant="outlined"
            label={`${row.passes.length} passed`}
          />
          <Chip
            size="small"
            color={
              rulesetMissing ? "default" : isRegression ? "error" : "default"
            }
            variant={rulesetMissing ? "outlined" : "filled"}
            label={`${row.regressions.length} failed`}
          />
          {row.unexpected_matches.length > 0 && (
            <Tooltip
              title={
                "A rule matched this patient that was not in the saved " +
                "list of expected matches. This may be fine -- or it " +
                "may mean a rule has started matching patients it " +
                "should not. Open the row to check."
              }
              arrow
            >
              <Chip
                size="small"
                color="warning"
                label={`${row.unexpected_matches.length} new match`}
              />
            </Tooltip>
          )}
          {rulesetMissing && row.passes.length > 0 && (
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label="pass is by accident"
              aria-label={
                "This patient was saved as 'rule should NOT match'. " +
                "With no rules loaded the engine answers 'no' to " +
                "everything, so the pass is by accident, not a real " +
                "check."
              }
            />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 1.5, pt: 0 }}>
        {row.error && (
          <Alert severity="error" sx={{ mb: 1 }}>
            {row.error}
          </Alert>
        )}
        <PatientSummary
          patient={patient}
          fallbackId={row.patient_id}
          rules={rules}
        />
        {row.regressions.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              What did not match
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mb: 0.75 }}
            >
              For each rule below: what we expected, what the engine
              found, and which part of the rule made the difference.
            </Typography>
            <Stack spacing={1}>
              {row.regressions.map((reg) => (
                <RegressionDetail
                  key={reg.rule_id}
                  ruleId={reg.rule_id}
                  fires={reg.fires}
                  expected={reg.expected}
                  rule={rules?.[reg.rule_id]}
                  patient={patient}
                  scopeType={scopeType}
                  scopeId={scopeId}
                  rulesetVersion={rulesetVersion}
                  rulesetMissing={rulesetMissing}
                  prebakedDiagnostic={reg.diagnostic ?? null}
                />
              ))}
            </Stack>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
}

function PatientSummary({
  patient,
  fallbackId,
  rules,
}: {
  patient?: ReplayPatientSummary;
  fallbackId: string;
  rules?: Record<string, RuleContext>;
}) {
  if (!patient) {
    return (
      <Typography variant="caption" color="text.secondary">
        Patient {fallbackId} -- open the test patient library to see codes,
        age and sex.
      </Typography>
    );
  }
  const ageSex = [
    typeof patient.age === "number" ? `${patient.age} years` : null,
    patient.sex ? patient.sex : null,
  ]
    .filter(Boolean)
    .join(", ");
  const codes = patient.codes ?? [];
  const description = patient.description
    ? friendlyDescription(patient.description, rules)
    : "";
  return (
    <Box>
      <Typography variant="subtitle2">The patient</Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
          {description}
        </Typography>
      )}
      {ageSex && (
        <Typography variant="caption" color="text.secondary">
          {ageSex}
        </Typography>
      )}
      {codes.length > 0 && (
        <Stack
          direction="row"
          spacing={0.5}
          flexWrap="wrap"
          sx={{ mt: 0.75, rowGap: 0.5 }}
        >
          {codes.map((code) => (
            <Chip
              key={code}
              size="small"
              variant="outlined"
              label={code}
              sx={{ fontFamily: "monospace", fontSize: "0.7rem" }}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}

interface RegressionDetailProps {
  ruleId: string;
  fires: boolean;
  expected: boolean;
  rule?: RuleContext;
  patient?: ReplayPatientSummary;
  scopeType?: string;
  scopeId?: string;
  rulesetVersion: string | null;
  rulesetMissing?: boolean;
  prebakedDiagnostic?: DiagnoseResponse | null;
}

function RegressionDetail({
  ruleId,
  fires,
  expected,
  rule,
  patient,
  scopeType,
  scopeId,
  rulesetVersion,
  rulesetMissing,
  prebakedDiagnostic,
}: RegressionDetailProps) {
  const [diagState, setDiagState] = useState<{
    loading: boolean;
    data: DiagnoseResponse | null;
    error: string | null;
  }>(() =>
    prebakedDiagnostic
      ? { loading: false, data: prebakedDiagnostic, error: null }
      : { loading: false, data: null, error: null },
  );

  useEffect(() => {
    if (prebakedDiagnostic) {
      setDiagState({ loading: false, data: prebakedDiagnostic, error: null });
      return;
    }
    if (!patient) return;
    if (rulesetMissing) {
      setDiagState({ loading: false, data: null, error: null });
      return;
    }
    let cancelled = false;
    setDiagState({ loading: true, data: null, error: null });
    diagnose({
      rule_id: ruleId,
      patient: {
        codes: patient.codes ?? [],
        age: patient.age,
        sex: patient.sex,
        pathway_id: patient.pathway_id,
        name: patient.name,
        description: patient.description ?? "",
      },
      scope_type: scopeType ?? "global",
      scope_id: scopeId ?? "default",
      ruleset_version: rulesetVersion,
    })
      .then((data) => {
        if (cancelled) return;
        setDiagState({ loading: false, data, error: null });
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        const msg =
          exc instanceof Error
            ? exc.message
            : "Could not load rule diagnostic.";
        setDiagState({ loading: false, data: null, error: msg });
      });
    return () => {
      cancelled = true;
    };
  }, [
    ruleId,
    patient,
    scopeType,
    scopeId,
    rulesetVersion,
    rulesetMissing,
    prebakedDiagnostic,
  ]);

  const friendlyId = shortenRuleId(ruleId);
  const heading = rule?.name || diagState.data?.rule_name || friendlyId;
  return (
    <Box
      sx={{
        p: 1,
        borderRadius: 1,
        border: "1px solid",
        borderColor: "error.100",
        bgcolor: "background.paper",
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {heading}
        </Typography>
        <Chip
          size="small"
          color="error"
          variant="outlined"
          label={`Expected: ${
            expected ? "should match" : "should NOT match"
          } -- Found: ${fires ? "matches" : "does not match"}`}
          aria-label={`Expected ${
            expected ? "should match" : "should NOT match"
          }, found ${fires ? "matches" : "does not match"}`}
        />
      </Stack>
      {rule?.recommendation_text && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.5 }}
        >
          {rule.recommendation_text}
        </Typography>
      )}
      {!rule?.name && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.25 }}
        >
          Rule id: {ruleId}
        </Typography>
      )}
      <DiagnosticBody state={diagState} />
    </Box>
  );
}

function DiagnosticBody({
  state,
}: {
  state: {
    loading: boolean;
    data: DiagnoseResponse | null;
    error: string | null;
  };
}) {
  if (state.loading) {
    return (
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ mt: 0.75 }}
      >
        <CircularProgress size={14} />
        <Typography variant="caption" color="text.secondary">
          Checking this patient against the rule...
        </Typography>
      </Stack>
    );
  }
  if (state.error) {
    return (
      <Alert severity="warning" sx={{ mt: 0.75 }}>
        {state.error}
      </Alert>
    );
  }
  if (state.data?.not_compiled) {
    return (
      <RulesetNotCompiledBanner
        scopeType={state.data.scope_type}
        scopeId={state.data.scope_id}
        detail={state.data.recompile_hint || state.data.message}
      />
    );
  }
  const tree = state.data?.annotated_tree;
  if (!tree) {
    return (
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 0.5 }}
      >
        {state.data?.message ||
          "Per-rule diagnostic skipped -- compile the bitmap and replay to see which leaf stopped matching."}
      </Typography>
    );
  }
  return (
    <Box sx={{ mt: 0.75 }}>
      <Divider sx={{ my: 0.5 }} />
      <Typography variant="caption" color="text.secondary">
        Here is each part of the rule. A green tick means this part
        matched the patient. A red cross means it did not.
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 0, listStyle: "none" }}>
        <DiagnoseNodeRow node={tree} depth={0} />
      </Box>
    </Box>
  );
}

interface DiagnoseNodeRowProps {
  node: DiagnoseNode;
  depth: number;
}

function DiagnoseNodeRow({ node, depth }: DiagnoseNodeRowProps) {
  const matched = !!node.matched;
  const isLeaf = node.kind === "CONCEPT" || node.kind === "DEMOGRAPHIC";
  const label = describeNode(node);
  const meta = describeMeta(node);
  return (
    <Box
      component="li"
      sx={{ pl: depth === 0 ? 0 : 2, mt: depth === 0 ? 0 : 0.25 }}
    >
      <Stack direction="row" alignItems="flex-start" spacing={0.75}>
        {matched ? (
          <CheckCircleOutlineIcon
            fontSize="small"
            color="success"
            aria-label="satisfied"
          />
        ) : (
          <CancelOutlinedIcon
            fontSize="small"
            color="error"
            aria-label="not satisfied"
          />
        )}
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="body2"
            color={matched ? "text.primary" : "error.main"}
            sx={{ fontWeight: isLeaf ? 400 : 600 }}
          >
            {label}
          </Typography>
          {meta && (
            <Typography variant="caption" color="text.secondary">
              {meta}
            </Typography>
          )}
          {node.missing_bitmap && (
            <Typography variant="caption" color="warning.main">
              The engine is missing data for this part of the rule.
              Please rebuild the rules.
            </Typography>
          )}
        </Box>
      </Stack>
      {node.children && node.children.length > 0 && (
        <Box component="ul" sx={{ m: 0, pl: 0, listStyle: "none" }}>
          {node.children.map((child, i) => (
            <DiagnoseNodeRow
              key={`${child.node_id ?? i}`}
              node={child}
              depth={depth + 1}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}

function describeNode(node: DiagnoseNode): string {
  if (node.kind === "CONCEPT") {
    const c = node.criterion ?? {};
    return c.preferred_term || c.term || c.snomed_concept_id || "Concept";
  }
  if (node.kind === "DEMOGRAPHIC") {
    if (node.field === "age") {
      return `Age ${node.operator ?? ""} ${node.value ?? ""}${
        node.unit ? ` ${node.unit}` : ""
      }`.trim();
    }
    if (node.field === "sex") {
      return `Sex = ${String(node.value ?? "")}`;
    }
    return node.field || "Demographic";
  }
  if (node.kind === "AT_LEAST") {
    return `At least ${node.min ?? 1} of the following`;
  }
  if (node.kind === "AND") return "All of the following";
  if (node.kind === "OR") return "Any of the following";
  if (node.kind === "NOT") return "None of the following";
  if (node.kind === "CONCEPT_GROUP") {
    return `${node.mode ?? "GROUP"} group`;
  }
  return node.kind;
}

function describeMeta(node: DiagnoseNode): string | null {
  if (node.kind === "AT_LEAST") {
    return `${node.matched_count ?? 0} of ${node.total_count ?? 0} satisfied (need ${node.min ?? 1})`;
  }
  if (node.kind === "AND" || node.kind === "OR") {
    return `${node.matched_count ?? 0} of ${node.total_count ?? 0} satisfied`;
  }
  if (
    node.kind === "CONCEPT" &&
    typeof node.match_count === "number" &&
    node.match_count > 1
  ) {
    return `Patient has ${node.match_count} codes that match this concept.`;
  }
  return null;
}

function shortenRuleId(ruleId: string): string {
  const tail = ruleId.split(":").pop() ?? ruleId;
  return `Rule ${tail}`;
}

/**
 * Strip raw rule IDs out of a saved patient description and replace
 * each one with the friendliest label we have for that rule.
 *
 * The scaffolder used to embed the full rule_id (for example
 * ``rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59``)
 * into the description. We now write a friendly label at scaffold
 * time, but every patient saved before that change still carries
 * the raw id. This helper rescues those rows at render time so the
 * reviewer never has to read a rule_id (per
 * .cursor/rules/health-literacy.mdc).
 *
 * Lookup order for the replacement, mirroring the backend's
 * ``_friendly_rule_label``:
 *
 *   1. ``rules[rule_id].name``               -- exact id match
 *   2. ``rules[stem].name``                  -- stem match (handles
 *                                                rule edits where
 *                                                ``:edit:NNNN``
 *                                                suffixes accumulate)
 *   3. ``rules[*].recommendation_text``      -- trimmed to ~120 chars
 *   4. fall back to "the rule" so we never leak the raw id
 *
 * Exported so the unit test can pin the substitution behaviour
 * without having to drive the full Accordion expansion through
 * JSDOM (Accordion is wrapped in a Collapse transition that does
 * not always settle in the testing environment).
 */
export function friendlyDescription(
  description: string,
  rules?: Record<string, RuleContext>,
): string {
  // Match an optional preceding "rule " word so "for rule rule:..."
  // collapses to 'for "<friendly>"' instead of the awkward
  // 'for rule "<friendly>"'.
  const RULE_ID_PATTERN = /\b(?:rule\s+)?(rule:[A-Za-z0-9_:.-]+)/g;
  return description.replace(RULE_ID_PATTERN, (_match, rawId: string) => {
    return friendlyRuleLabel(rawId, rules);
  });
}

function friendlyRuleLabel(
  ruleId: string,
  rules?: Record<string, RuleContext>,
): string {
  const lookup = rules ?? {};
  const exact = lookup[ruleId];
  if (exact?.name) return `"${exact.name}"`;
  if (exact?.recommendation_text) return shortenRecommendation(exact.recommendation_text);

  // Stem match -- ``rule:NG12:...:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59``
  // collapses to ``rule:NG12:...:R004:6d4e9c13`` so we still find a
  // name when the saved description pinned a pre-edit id.
  const stemIdx = ruleId.indexOf(":edit:");
  const stem = stemIdx >= 0 ? ruleId.slice(0, stemIdx) : ruleId;
  if (stem !== ruleId) {
    const stemHit = lookup[stem];
    if (stemHit?.name) return `"${stemHit.name}"`;
    if (stemHit?.recommendation_text) {
      return shortenRecommendation(stemHit.recommendation_text);
    }
    for (const [key, value] of Object.entries(lookup)) {
      if (!key.startsWith(`${stem}:edit:`) && key !== stem) continue;
      if (value?.name) return `"${value.name}"`;
      if (value?.recommendation_text) {
        return shortenRecommendation(value.recommendation_text);
      }
    }
  }

  return "the rule";
}

function shortenRecommendation(text: string): string {
  const firstLine = text.split("\n")[0].trim().replace(/[:.]+$/, "");
  if (firstLine.length <= 120) return `"${firstLine}"`;
  return `"${firstLine.slice(0, 117).trimEnd()}..."`;
}

type IntentColor = "success" | "default" | "warning";

interface PatientIntent {
  label: string;
  color: IntentColor;
  tooltip: string;
}

function computePatientIntent(row: ReplayPatientResult): PatientIntent {
  const all = [...row.passes, ...row.regressions];
  const positives = all.filter((a) => a.expected).length;
  const negatives = all.filter((a) => !a.expected).length;
  if (positives > 0 && negatives === 0) {
    return {
      label: "should match",
      color: "success",
      tooltip: "This patient was saved as 'the rule SHOULD match'.",
    };
  }
  if (negatives > 0 && positives === 0) {
    return {
      label: "should NOT match",
      color: "default",
      tooltip:
        "This patient was saved as 'the rule should NOT match'. " +
        "A pass here means the rule correctly did not match.",
    };
  }
  if (positives > 0 && negatives > 0) {
    return {
      label: "mixed",
      color: "warning",
      tooltip:
        `Saved with ${positives} 'should match' and ${negatives} ` +
        "'should NOT match' checks. Open the row to see which.",
    };
  }
  return {
    label: "no checks saved",
    color: "warning",
    tooltip:
      "This patient has no saved expectations. We cannot test " +
      "anything until you add at least one expected outcome.",
  };
}
