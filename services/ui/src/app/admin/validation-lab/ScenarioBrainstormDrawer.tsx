/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A0ADDB38
 *   DI: DI-EB716E68
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")
 */
"use client";

/**
 * Guided Validation Lab scenario-variant brainstorm drawer.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
 */

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import LoadedGuidelineAutocomplete, {
  type LoadedGuidelineOption,
} from "../guidance/LoadedGuidelineAutocomplete";
import RecommendationPickerDialog, {
  type AttachedRecommendation,
} from "../guidance/RecommendationPickerDialog";
import {
  brainstorm,
  createCase,
  type BrainstormQuestion,
  type BrainstormRecommendation,
} from "./labApi";
import {
  createCasesFromVariants,
  normaliseVariantFromApi,
  type CreateCaseResult,
  type ScenarioVariant,
} from "./scenarioVariants";
import ScenarioBrainstormVariantsStep from "./ScenarioBrainstormVariantsStep";

const STEPS = ["Attach", "Clarify", "Variants", "Review"];
/** Keep in sync with libs/validation_lab/scenario_patch.MAX_BRAINSTORM_RECOMMENDATIONS */
const MAX_BRAINSTORM_RECOMMENDATIONS = 5;

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated?: (caseIds: string[]) => void;
}

export default function ScenarioBrainstormDrawer({
  open,
  onClose,
  onCreated,
}: Props) {
  const [step, setStep] = useState(0);
  const [scenarioText, setScenarioText] = useState("");
  const [selectedGuideline, setSelectedGuideline] =
    useState<LoadedGuidelineOption | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [recommendations, setRecommendations] = useState<
    BrainstormRecommendation[]
  >([]);
  const [questions, setQuestions] = useState<BrainstormQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [clarifyRound, setClarifyRound] = useState(0);
  const [guidance, setGuidance] = useState("");
  const [variants, setVariants] = useState<ScenarioVariant[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [includeControl, setIncludeControl] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [createResults, setCreateResults] = useState<CreateCaseResult[]>([]);

  const selectedVariants = useMemo(
    () => variants.filter((v) => selectedIds.has(v.variantId)),
    [variants, selectedIds],
  );

  function reset() {
    setStep(0);
    setScenarioText("");
    setSelectedGuideline(null);
    setRecommendations([]);
    setQuestions([]);
    setAnswers({});
    setClarifyRound(0);
    setGuidance("");
    setVariants([]);
    setSelectedIds(new Set());
    setIncludeControl(false);
    setError("");
    setCreateResults([]);
  }

  async function runUnderstand() {
    setBusy(true);
    setError("");
    try {
      const res = await brainstorm({
        phase: "understand",
        scenario_text: scenarioText,
        recommendations,
      });
      setGuidance(res.guidance_message || "");
      if (res.needs_clarification && (res.questions || []).length > 0) {
        setQuestions(res.questions || []);
        setStep(1);
      } else if (res.guidance_message && !(res.questions || []).length) {
        setStep(0);
      } else {
        await runPropose(res.recommendations || recommendations);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runClarify(skip = false) {
    setBusy(true);
    setError("");
    try {
      const nextRound = skip ? 2 : clarifyRound + 1;
      const res = await brainstorm({
        phase: "clarify",
        scenario_text: scenarioText,
        recommendations,
        answers: skip ? {} : answers,
        round: nextRound,
      });
      setClarifyRound(nextRound);
      setGuidance(res.guidance_message || "");
      if (res.needs_clarification && (res.questions || []).length > 0) {
        setQuestions(res.questions || []);
        setStep(1);
      } else {
        await runPropose(res.recommendations || recommendations);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runPropose(recs: BrainstormRecommendation[]) {
    setBusy(true);
    setError("");
    try {
      const res = await brainstorm({
        phase: "propose_variants",
        scenario_text: scenarioText,
        recommendations: recs,
        answers,
        include_control: includeControl,
      });
      setGuidance(res.guidance_message || "");
      const next = (res.variants || []).map((v, index) =>
        normaliseVariantFromApi(v as Record<string, unknown>, index),
      );
      setVariants(next);
      // Default: select every proposed variant so Create N matches the
      // full brainstorm set; user can uncheck before create.
      setSelectedIds(new Set(next.map((v) => v.variantId)));
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate() {
    setBusy(true);
    setError("");
    try {
      const results = await createCasesFromVariants(
        selectedVariants,
        createCase,
      );
      setCreateResults(results);
      setStep(3);
      const okIds = results
        .filter((r) => r.ok && r.caseId)
        .map((r) => r.caseId as string);
      if (okIds.length) onCreated?.(okIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function toggleAnswer(qid: string, oid: string, multi: boolean, max: number) {
    setAnswers((prev) => {
      const current = prev[qid] || [];
      if (!multi) return { ...prev, [qid]: [oid] };
      if (current.includes(oid)) {
        return { ...prev, [qid]: current.filter((x) => x !== oid) };
      }
      if (current.length >= max) return prev;
      return { ...prev, [qid]: [...current, oid] };
    });
  }

  function toggleVariant(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 2 } }}
    >
      <Box data-testid="scenario-brainstorm-drawer">
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">Brainstorm scenario</Typography>
        <IconButton
          aria-label="Close brainstorm"
          onClick={() => {
            reset();
            onClose();
          }}
        >
          <CloseIcon />
        </IconButton>
      </Stack>
      <Stepper activeStep={step} alternativeLabel sx={{ my: 2 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
      {error ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      ) : null}
      {guidance ? (
        <Alert severity="info" sx={{ mb: 1 }}>
          {guidance}
        </Alert>
      ) : null}

      {step === 0 ? (
        <Stack spacing={1.5}>
          <TextField
            label="Scenario text"
            multiline
            minRows={4}
            value={scenarioText}
            onChange={(e) => setScenarioText(e.target.value)}
            fullWidth
          />
          <Typography variant="body2" color="text.secondary">
            Attach recommendations from guidelines already in the knowledge
            graph (same list as Clinical Guidelines).
          </Typography>
          <LoadedGuidelineAutocomplete
            valueCode={selectedGuideline?.code || null}
            onChange={setSelectedGuideline}
            label="Guideline in knowledge graph"
            helperText="What is in the knowledge graph -- Clinical Guidelines"
            testId="brainstorm-guideline-autocomplete"
            inputTestId="brainstorm-guideline-lookup"
          />
          <Button
            variant="outlined"
            disabled={!selectedGuideline}
            onClick={() => setPickerOpen(true)}
            data-testid="brainstorm-attach-recommendations"
          >
            Attach recommendations
          </Button>
          {recommendations.length > 0 ? (
            <Typography variant="body2">
              Attached: {recommendations.length} recommendation
              {recommendations.length === 1 ? "" : "s"}
              {` (max ${MAX_BRAINSTORM_RECOMMENDATIONS})`}
            </Typography>
          ) : null}
          {recommendations.length > MAX_BRAINSTORM_RECOMMENDATIONS ? (
            <Alert severity="warning">
              Brainstorm can use at most {MAX_BRAINSTORM_RECOMMENDATIONS}{" "}
              recommendations at a time (about 3 test cases each). Remove some
              before continuing -- Select all on a whole guideline is too many.
            </Alert>
          ) : null}
          <FormControlLabel
            control={
              <Checkbox
                checked={includeControl}
                onChange={(e) => setIncludeControl(e.target.checked)}
              />
            }
            label="Include one optional control variant (across the batch)"
          />
          <Button
            variant="contained"
            disabled={
              busy ||
              (!scenarioText.trim() && !recommendations.length) ||
              recommendations.length > MAX_BRAINSTORM_RECOMMENDATIONS
            }
            onClick={() => void runUnderstand()}
          >
            {busy ? <CircularProgress size={18} /> : "Continue"}
          </Button>
        </Stack>
      ) : null}

      {step === 1 ? (
        <Stack spacing={1.5}>
          <Typography variant="subtitle2" component="h6">
            Clarify
          </Typography>
          {questions.map((q) => {
            const multi = Boolean(q.allowMultiple);
            const max = q.maxSelections || (multi ? 99 : 1);
            const chosen = answers[q.id] || [];
            return (
              <Box key={q.id} sx={{ border: "1px solid", borderColor: "divider", p: 1 }}>
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  {q.question}
                  {multi ? ` (pick up to ${max})` : ""}
                </Typography>
                {q.options.map((opt) => (
                  <FormControlLabel
                    key={opt.id}
                    control={
                      <Checkbox
                        checked={chosen.includes(opt.id)}
                        onChange={() =>
                          toggleAnswer(q.id, opt.id, multi, max)
                        }
                      />
                    }
                    label={
                      opt.recommended
                        ? `${opt.label} (recommended)`
                        : opt.label
                    }
                  />
                ))}
              </Box>
            );
          })}
          {recommendations.length > MAX_BRAINSTORM_RECOMMENDATIONS ? (
            <Alert severity="warning">
              Too many recommendations attached (
              {recommendations.length}). Go back and keep at most{" "}
              {MAX_BRAINSTORM_RECOMMENDATIONS} before generating variants.
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1}>
            <Button
              onClick={() => {
                setError("");
                setStep(0);
              }}
              disabled={busy}
            >
              Back
            </Button>
            <Button onClick={() => void runClarify(true)} disabled={busy}>
              Skip
            </Button>
            <Button
              variant="contained"
              onClick={() => void runClarify(false)}
              disabled={
                busy ||
                recommendations.length > MAX_BRAINSTORM_RECOMMENDATIONS
              }
            >
              {busy ? <CircularProgress size={18} /> : "Next"}
            </Button>
          </Stack>
        </Stack>
      ) : null}

      {step === 2 ? (
        <ScenarioBrainstormVariantsStep
          variants={variants}
          selectedIds={selectedIds}
          selectedCount={selectedVariants.length}
          guidance={guidance}
          busy={busy}
          onToggle={toggleVariant}
          onRetry={() => void runPropose(recommendations)}
          onCreate={() => void handleCreate()}
        />
      ) : null}

      {step === 3 ? (
        <Stack spacing={1}>
          <Typography variant="subtitle2">Review</Typography>
          {createResults.map((r) => (
            <Alert key={r.variantId} severity={r.ok ? "success" : "error"}>
              {r.variantId}: {r.ok ? `created ${r.caseId}` : r.error}
            </Alert>
          ))}
          <Button
            variant="contained"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Done
          </Button>
        </Stack>
      ) : null}

      {pickerOpen && selectedGuideline ? (
        <RecommendationPickerDialog
          code={selectedGuideline.code}
          guidelineTitle={selectedGuideline.title || selectedGuideline.code}
          source={selectedGuideline.guideline_source}
          mode="attach"
          onClose={() => setPickerOpen(false)}
          onRulesGenerated={() => undefined}
          onAttach={(recs: AttachedRecommendation[]) => {
            // Prefer compiled, then approved, so Select all still yields
            // the most useful subset when over the cap.
            const ranked = [...recs].sort((a, b) => {
              const score = (r: AttachedRecommendation) => {
                const status = String(r.ruleStatus || "");
                if (status === "active") return 2;
                if (status) return 1;
                return 0;
              };
              return score(b) - score(a);
            });
            const next = ranked.slice(0, MAX_BRAINSTORM_RECOMMENDATIONS);
            setRecommendations(next);
            if (recs.length > MAX_BRAINSTORM_RECOMMENDATIONS) {
              setError(
                `Kept ${MAX_BRAINSTORM_RECOMMENDATIONS} of ${recs.length} selected (approved rules preferred). Brainstorm allows at most ${MAX_BRAINSTORM_RECOMMENDATIONS} at a time.`,
              );
            } else {
              setError("");
            }
            setPickerOpen(false);
          }}
        />
      ) : null}
      </Box>
    </Drawer>
  );
}
