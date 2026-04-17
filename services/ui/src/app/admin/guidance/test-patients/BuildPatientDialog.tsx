"use client";

/**
 * BuildPatientDialog -- reviewer builds a synthetic patient and
 * dry-runs it against the live ruleset before saving.
 *
 * Save is disabled until at least one dry-run has been completed,
 * which is the "see, then confirm" requirement.  Per-rule expectation
 * toggles (Fires / Does not fire / Skip) drive what gets snapshotted.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import ConceptSearchPanel from "../EditRuleDialog/ConceptSearchPanel";
import { friendlyTerm } from "../EditRuleDialog/copy";
import type { LogicCriterion } from "../EditRuleDialog/types";

import { dryRun, savePatient } from "./api";
import type {
  DryRunResponse,
  ExpectationInput,
  PatientPayload,
} from "./types";

interface SearchHit {
  snomed_concept_id: string;
  preferred_term: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  guidelineId: string;
  initialPatient?: Partial<PatientPayload>;
  initialExpectations?: ExpectationInput[];
  onSaved?: (id: string) => void;
}

type Decision = "fires" | "no_fire" | "skip";

const EMPTY_PATIENT: PatientPayload = {
  codes: [],
  age: null,
  sex: null,
  pathway_id: null,
  name: "",
  description: "",
  generation_source: "manual",
};

export default function BuildPatientDialog({
  open,
  onClose,
  guidelineId,
  initialPatient,
  initialExpectations,
  onSaved,
}: Props) {
  const [patient, setPatient] = useState<PatientPayload>({
    ...EMPTY_PATIENT,
    ...initialPatient,
  });
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [dryRunResult, setDryRunResult] = useState<DryRunResponse | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [loadingDryRun, setLoadingDryRun] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<string | null>(null);
  const autoCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearAutoClose = useCallback(() => {
    if (autoCloseTimer.current !== null) {
      clearTimeout(autoCloseTimer.current);
      autoCloseTimer.current = null;
    }
  }, []);

  useEffect(() => {
    if (!open) {
      clearAutoClose();
      return;
    }
    setPatient({ ...EMPTY_PATIENT, ...initialPatient });
    setDryRunResult(null);
    const seed: Record<string, Decision> = {};
    (initialExpectations || []).forEach((e) => {
      seed[e.rule_id] = e.fires ? "fires" : "no_fire";
    });
    setDecisions(seed);
    setError(null);
    setSaveResult(null);
  }, [open, initialPatient, initialExpectations, clearAutoClose]);

  useEffect(() => clearAutoClose, [clearAutoClose]);

  const addCode = useCallback((criterion: LogicCriterion) => {
    setPatient((p) => {
      if (p.codes.includes(criterion.snomed_concept_id)) return p;
      return { ...p, codes: [...p.codes, criterion.snomed_concept_id] };
    });
    setHits((prev) => {
      if (prev.some((h) => h.snomed_concept_id === criterion.snomed_concept_id)) {
        return prev;
      }
      return [
        ...prev,
        {
          snomed_concept_id: criterion.snomed_concept_id,
          preferred_term: criterion.preferred_term,
        },
      ];
    });
    setDryRunResult(null);
  }, []);

  const removeCode = useCallback((cid: string) => {
    setPatient((p) => ({ ...p, codes: p.codes.filter((c) => c !== cid) }));
    setDryRunResult(null);
  }, []);

  const handleDryRun = useCallback(async () => {
    setLoadingDryRun(true);
    setError(null);
    try {
      const resp = await dryRun({
        patient,
        scope_type: "guideline",
        scope_id: guidelineId,
      });
      setDryRunResult(resp);
      setDecisions((prev) => {
        const next = { ...prev };
        resp.matched_rules.forEach((r) => {
          if (next[r.rule_id] === undefined) next[r.rule_id] = "fires";
        });
        return next;
      });
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not run the patient. Please try again."
      );
    } finally {
      setLoadingDryRun(false);
    }
  }, [patient, guidelineId]);

  const expectations: ExpectationInput[] = useMemo(() => {
    if (!dryRunResult) return [];
    const out: ExpectationInput[] = [];
    Object.entries(decisions).forEach(([ruleId, dec]) => {
      if (dec === "skip") return;
      out.push({
        rule_id: ruleId,
        fires: dec === "fires",
        matched_branch_node_ids: dryRunResult.branch_paths[ruleId] || [],
      });
    });
    return out;
  }, [decisions, dryRunResult]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await savePatient({
        patient,
        guideline_id: guidelineId,
        scope_type: "guideline",
        scope_id: guidelineId,
        expectations,
        ruleset_version: dryRunResult?.ruleset_version || null,
      });
      setSaveResult(
        result.created
          ? `Saved as ${result.id} with ${result.expectations_written} expectation(s). Closing...`
          : `An identical patient already exists (${result.id}). Nothing was saved.`
      );
      if (result.created && onSaved) onSaved(result.id);
      if (result.created) {
        clearAutoClose();
        autoCloseTimer.current = setTimeout(() => {
          autoCloseTimer.current = null;
          onClose();
        }, 1500);
      }
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not save the patient. Please try again."
      );
    } finally {
      setSaving(false);
    }
  }, [
    patient,
    guidelineId,
    expectations,
    dryRunResult,
    onSaved,
    onClose,
    clearAutoClose,
  ]);

  const codeLabel = (cid: string): string => {
    const hit = hits.find((h) => h.snomed_concept_id === cid);
    return hit ? friendlyTerm(hit.preferred_term) : cid;
  };

  const canSave = !!dryRunResult && !saving && expectations.length >= 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Build a test patient</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Pick the symptoms or signs this patient has, set their age and sex,
            then run a dry run to see which rules they match. You can then save
            the patient as a test for future updates.
          </Typography>

          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField
              size="small"
              label="Name (optional)"
              value={patient.name}
              onChange={(e) => setPatient({ ...patient, name: e.target.value })}
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label="Age (years)"
              type="number"
              value={patient.age ?? ""}
              onChange={(e) =>
                setPatient({
                  ...patient,
                  age: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              sx={{ width: 160 }}
            />
            <TextField
              select
              size="small"
              label="Sex"
              value={patient.sex || ""}
              onChange={(e) =>
                setPatient({ ...patient, sex: (e.target.value || null) as PatientPayload["sex"] })
              }
              sx={{ width: 160 }}
            >
              <MenuItem value="">Not given</MenuItem>
              <MenuItem value="female">Female</MenuItem>
              <MenuItem value="male">Male</MenuItem>
              <MenuItem value="other">Other</MenuItem>
            </TextField>
          </Stack>

          <Box>
            <Typography variant="caption" color="text.secondary">
              Symptoms or signs ({patient.codes.length})
            </Typography>
            <Box sx={{ mt: 0.5, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {patient.codes.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  None yet. Use the search below to add some.
                </Typography>
              ) : (
                patient.codes.map((cid) => (
                  <Chip
                    key={cid}
                    label={codeLabel(cid)}
                    size="small"
                    onDelete={() => removeCode(cid)}
                    aria-label={`${codeLabel(cid)} -- click X to remove`}
                  />
                ))
              )}
            </Box>
          </Box>

          <Box sx={{ border: "1px solid", borderColor: "divider", p: 1.5, borderRadius: 1 }}>
            <ConceptSearchPanel
              mode="add"
              focusLabel={null}
              initialQuery=""
              onPick={addCode}
            />
          </Box>

          <Stack direction="row" spacing={2} alignItems="center">
            <Button
              variant="contained"
              onClick={handleDryRun}
              disabled={loadingDryRun || patient.codes.length === 0}
              startIcon={loadingDryRun ? <CircularProgress size={16} /> : undefined}
            >
              {loadingDryRun ? "Running..." : "Dry run"}
            </Button>
            <Typography variant="caption" color="text.secondary">
              Save is locked until you run the patient at least once.
            </Typography>
          </Stack>

          {error && <Alert severity="error">{error}</Alert>}
          {saveResult && <Alert severity="success">{saveResult}</Alert>}

          {dryRunResult && (
            <Box>
              <Typography variant="subtitle2">
                Where this patient ends up ({dryRunResult.matched_rules.length} rule
                {dryRunResult.matched_rules.length === 1 ? "" : "s"} matched)
              </Typography>
              {dryRunResult.matched_rules.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  No rules matched. You can still save this patient to test that
                  no rules fire in future deployments.
                </Typography>
              ) : (
                <Stack spacing={1} sx={{ mt: 1 }}>
                  {dryRunResult.matched_rules.map((rule) => (
                    <ExpectationRow
                      key={rule.rule_id}
                      ruleId={rule.rule_id}
                      ruleName={rule.name || rule.rule_id}
                      branchCount={
                        (dryRunResult.branch_paths[rule.rule_id] || []).length
                      }
                      decision={decisions[rule.rule_id] || "fires"}
                      onChange={(d) =>
                        setDecisions((prev) => ({ ...prev, [rule.rule_id]: d }))
                      }
                    />
                  ))}
                </Stack>
              )}
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!canSave}
          startIcon={saving ? <CircularProgress size={16} /> : undefined}
        >
          {saving ? "Saving..." : "Save patient"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

interface ExpectationRowProps {
  ruleId: string;
  ruleName: string;
  branchCount: number;
  decision: Decision;
  onChange: (d: Decision) => void;
}

function ExpectationRow({
  ruleId,
  ruleName,
  branchCount,
  decision,
  onChange,
}: ExpectationRowProps) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={1.5}
      alignItems={{ xs: "flex-start", sm: "center" }}
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: "grey.50",
        border: "1px solid",
        borderColor: "grey.200",
      }}
    >
      <Box sx={{ flex: 1 }}>
        <Typography variant="body2">{ruleName}</Typography>
        <Typography variant="caption" color="text.secondary">
          {ruleId} -- {branchCount} branch{branchCount === 1 ? "" : "es"} matched
        </Typography>
      </Box>
      <ToggleButtonGroup
        size="small"
        value={decision}
        exclusive
        onChange={(_, value) => value && onChange(value as Decision)}
        aria-label={`Expectation for rule ${ruleName}`}
      >
        <ToggleButton value="fires" aria-label="should fire">
          Should fire
        </ToggleButton>
        <ToggleButton value="no_fire" aria-label="should not fire">
          Should not fire
        </ToggleButton>
        <ToggleButton value="skip" aria-label="do not assert">
          Skip
        </ToggleButton>
      </ToggleButtonGroup>
    </Stack>
  );
}
