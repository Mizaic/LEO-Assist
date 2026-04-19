"use client";

/**
 * ReplayResultsDialog -- show the most recent regression report or a
 * fresh on-demand replay run.  Splits results into pass / regression /
 * drift so reviewers can spot silent rule changes at a glance.
 *
 * Each result row is expandable.  When the row contains a regression
 * we call ``/api/guidance/test-patients/diagnose`` -- which is backed
 * by the SAME roaring-bitmap evaluator that production uses to fire
 * rules -- so the per-leaf diagnostic is guaranteed to agree with the
 * live firing decision.  The annotated tree is rendered hierarchically
 * (preserving AND / OR / NOT / AT_LEAST grouping) so the reviewer can
 * see exactly which branch of the rule did or did not fire.
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
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ flex: 1 }}>
            {isSandbox
              ? "Replay results -- unsaved draft (sandbox)"
              : "Replay results -- live ruleset"}
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
            ? "These results came from a throwaway compile of the rule you are currently editing. Production was NOT touched."
            : "These results came from the rule that is currently deployed in production (the bitmap in Redis)."}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        {!report ? (
          <Typography variant="body2" color="text.secondary">
            Run a replay to see results here.
          </Typography>
        ) : (
          <Stack spacing={2}>
            <ReportHeaderChips
              report={report}
              rulesetMissing={reportRulesetMissing(report)}
            />

            {reportRulesetMissing(report) && (
              <RulesetNotCompiledBanner
                scopeType={report.scope_type}
                scopeId={report.scope_id}
                detail={
                  "Every patient hit the same 'no active ruleset' error " +
                  "from the evaluator. EVERY rule returns 'does not fire', " +
                  "so any patient whose saved expectation was 'must NOT " +
                  "match' (boundary cases, negative pairs) shows '1 pass' " +
                  "by coincidence -- those passes are NOT verifying " +
                  "anything. Patients whose saved expectation was 'must " +
                  "match' show '1 regress'. Compile the bitmap and re-run " +
                  "the replay before trusting any verdict in this report."
                }
              />
            )}

            {report.regressions_count > 0 && (
              <Alert severity="error">
                {report.regressions_count} test patient assertion
                {report.regressions_count === 1 ? "" : "s"} no longer match.
                Open a row below to see the patient and which part of the
                rule stopped matching.
              </Alert>
            )}

            <Box>
              <Typography variant="subtitle2">By patient</Typography>
              <Stack spacing={1} sx={{ mt: 1 }}>
                {report.results.map((row) => (
                  <PatientResultRow
                    key={row.patient_id}
                    row={row}
                    patient={patientsById[row.patient_id]}
                    rules={rules}
                    scopeType={scopeType}
                    scopeId={scopeId}
                    rulesetVersion={report.ruleset_version}
                    rulesetMissing={reportRulesetMissing(report)}
                  />
                ))}
              </Stack>
            </Box>
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

function ReportHeaderChips({
  report,
  rulesetMissing,
}: {
  report: ReplayReport;
  rulesetMissing: boolean;
}) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
      <Chip
        color={
          rulesetMissing
            ? "default"
            : report.regressions_count === 0
              ? "success"
              : "error"
        }
        variant={rulesetMissing ? "outlined" : "filled"}
        label={`${report.regressions_count} regression${
          report.regressions_count === 1 ? "" : "s"
        }`}
      />
      <Chip
        color={rulesetMissing ? "default" : "success"}
        variant="outlined"
        label={`${report.passes_count} pass${
          report.passes_count === 1 ? "" : "es"
        }`}
      />
      <Chip
        color={
          rulesetMissing
            ? "default"
            : report.drift_count === 0
              ? "default"
              : "warning"
        }
        variant="outlined"
        label={`${report.drift_count} drift`}
      />
      {rulesetMissing && (
        <Chip
          color="warning"
          label="Verdicts unreliable -- no ruleset compiled"
          aria-label="Verdicts unreliable because no ruleset is compiled"
        />
      )}
      {report.ruleset_version && (
        <Chip label={`Ruleset ${report.ruleset_version}`} variant="outlined" />
      )}
    </Stack>
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
            label={`${row.passes.length} pass`}
          />
          <Chip
            size="small"
            color={
              rulesetMissing ? "default" : isRegression ? "error" : "default"
            }
            variant={rulesetMissing ? "outlined" : "filled"}
            label={`${row.regressions.length} regress`}
          />
          {row.unexpected_matches.length > 0 && (
            <Chip
              size="small"
              color="warning"
              label={`${row.unexpected_matches.length} new match`}
            />
          )}
          {rulesetMissing && row.passes.length > 0 && (
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label="pass is coincidental"
              aria-label={
                "This patient's saved expectation was 'must NOT match'. " +
                "With no ruleset compiled the evaluator returns false " +
                "for everything, so the pass is coincidental, not a " +
                "verification."
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
        <PatientSummary patient={patient} fallbackId={row.patient_id} />
        {row.regressions.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              What stopped matching
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
}: {
  patient?: ReplayPatientSummary;
  fallbackId: string;
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
  return (
    <Box>
      <Typography variant="subtitle2">The patient</Typography>
      {patient.description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
          {patient.description}
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
          label={`expected ${expected ? "fires" : "does not fire"}, now ${
            fires ? "fires" : "does not fire"
          }`}
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
          Re-running the rule against this patient...
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
        Each part of the rule (evaluated by the bitmap engine):
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
              Bitmap missing in Redis -- recompile required.
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
    return `Patient has ${node.match_count} codes in this concept's SNOMED hierarchy.`;
  }
  return null;
}

function shortenRuleId(ruleId: string): string {
  const tail = ruleId.split(":").pop() ?? ruleId;
  return `Rule ${tail}`;
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
      label: "positive test",
      color: "success",
      tooltip: "Saved as 'rule MUST match this patient'.",
    };
  }
  if (negatives > 0 && positives === 0) {
    return {
      label: "negative test",
      color: "default",
      tooltip:
        "Saved as 'rule must NOT match this patient'. " +
        "A 'pass' here means the rule correctly did not over-fire.",
    };
  }
  if (positives > 0 && negatives > 0) {
    return {
      label: "mixed test",
      color: "warning",
      tooltip:
        `Saved with ${positives} 'must match' and ${negatives} ` +
        "'must NOT match' assertions. Open the row to see which.",
    };
  }
  return {
    label: "no assertions",
    color: "warning",
    tooltip:
      "This patient has no saved expectations. Replay cannot verify " +
      "anything until at least one rule expectation is added.",
  };
}
