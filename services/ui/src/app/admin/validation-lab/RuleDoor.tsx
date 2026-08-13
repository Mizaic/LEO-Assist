/**
 * Rule door: pick a guideline rule, check the letter, run the pipeline.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import CreatePatientWizard from "./CreatePatientWizard";
import {
  listGuidanceRules,
  type GuidanceRulePickerRow,
} from "./labFindingsApi";
import { createCase, type LabCase } from "./labApi";
import { DEFAULT_LAB_PLAN_ID } from "./labRun";
import type { RunReviewTarget } from "./RunReviewLightbox";
import { queueCasePipeline, pollCasePipeline } from "./labRun";

interface Props {
  seedPhrases?: string[];
  onBack: () => void;
  onReview: (target: RunReviewTarget) => void;
}

type Step = "pick" | "check" | "run";

export default function RuleDoor({ seedPhrases, onBack, onReview }: Props) {
  const [step, setStep] = useState<Step>("pick");
  const [rules, setRules] = useState<GuidanceRulePickerRow[]>([]);
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<GuidanceRulePickerRow | null>(null);
  const [letter, setLetter] = useState("");
  const [gpNote, setGpNote] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void listGuidanceRules()
      .then(setRules)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load rules"),
      );
  }, []);

  useEffect(() => {
    if (seedPhrases?.length) {
      setLetter(letterFromPhrases(seedPhrases));
      setStep("check");
    }
  }, [seedPhrases]);

  const filtered = uniqueByRuleId(
    rules.filter((row) => matchesRule(row, query)),
  ).slice(0, 40);

  async function onRun() {
    if (!letter.trim()) {
      setError("A referral letter is required.");
      return;
    }
    setBusy(true);
    setError("");
    setStep("run");
    try {
      const created = await createCase(caseFromRule(picked, letter, gpNote));
      const started = await queueCasePipeline(created.id, DEFAULT_LAB_PLAN_ID);
      onReview(reviewFromCase(created, started.id, started.status, letter, gpNote));
      const finalRun = await pollCasePipeline(created.id, started.id);
      onReview(
        reviewFromCase(created, finalRun.id, finalRun.status, letter, gpNote, true),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the run");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box data-testid="validation-lab-rule-door">
      <Button size="small" onClick={onBack} sx={{ mb: 2 }}>
        Back to start
      </Button>
      <Typography variant="h6" fontWeight={700} sx={{ mb: 0.5 }}>
        Test a guideline rule
      </Typography>
      {error ? <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert> : null}
      {step === "pick" ? (
        <PickRule
          query={query}
          onQuery={setQuery}
          rows={filtered}
          onPick={(row) => {
            setPicked(row);
            setLetter(letterFromRule(row));
            setStep("check");
          }}
          onAdvanced={() => {
            setLetter("Dear colleague,\n\n");
            setAdvanced(true);
            setStep("check");
          }}
        />
      ) : null}
      {step === "check" || step === "run" ? (
        <CheckCase
          letter={letter}
          gpNote={gpNote}
          onLetter={setLetter}
          onGpNote={setGpNote}
          advanced={advanced}
          onToggleAdvanced={() => setAdvanced((v) => !v)}
          busy={busy}
          onRun={() => void onRun()}
        />
      ) : null}
    </Box>
  );
}

function PickRule({
  query,
  onQuery,
  rows,
  onPick,
  onAdvanced,
}: {
  query: string;
  onQuery: (value: string) => void;
  rows: GuidanceRulePickerRow[];
  onPick: (row: GuidanceRulePickerRow) => void;
  onAdvanced: () => void;
}) {
  return (
    <Box>
      <TextField
        size="small"
        fullWidth
        label="Search rules"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        sx={{ mb: 2 }}
      />
      <Button onClick={onAdvanced} sx={{ mb: 2 }}>
        Advanced: edit the letter
      </Button>
      <Stack spacing={1} data-testid="validation-lab-rule-list">
        {rows.map((row) => (
          <Box
            key={row.rule_id}
            onClick={() => onPick(row)}
            sx={{
              p: 1.5,
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              cursor: "pointer",
            }}
          >
            <Typography variant="body2" fontWeight={700}>
              {row.name || row.rule_id}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.guideline_title} {row.recommendation_text || ""}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

function CheckCase({
  letter,
  gpNote,
  onLetter,
  onGpNote,
  advanced,
  onToggleAdvanced,
  busy,
  onRun,
}: {
  letter: string;
  gpNote: string;
  onLetter: (value: string) => void;
  onGpNote: (value: string) => void;
  advanced: boolean;
  onToggleAdvanced: () => void;
  busy: boolean;
  onRun: () => void;
}) {
  return (
    <Stack spacing={2} data-testid="validation-lab-check-case">
      <TextField
        label="Referral letter"
        value={letter}
        onChange={(e) => onLetter(e.target.value)}
        fullWidth
        multiline
        minRows={8}
        required
      />
      <TextField
        label="GP note (optional)"
        value={gpNote}
        onChange={(e) => onGpNote(e.target.value)}
        fullWidth
        multiline
        minRows={3}
      />
      <Stack direction="row" spacing={1}>
        <Button variant="contained" disabled={busy} onClick={onRun}>
          {busy ? "Starting..." : "Run pipeline"}
        </Button>
        <Button onClick={onToggleAdvanced}>
          {advanced ? "Hide advanced" : "Advanced: edit the letter"}
        </Button>
      </Stack>
      <Collapse in={advanced}>
        <CreatePatientWizard onCaseCreated={() => undefined} />
      </Collapse>
    </Stack>
  );
}

function uniqueByRuleId(
  rows: GuidanceRulePickerRow[],
): GuidanceRulePickerRow[] {
  const seen = new Set<string>();
  const unique: GuidanceRulePickerRow[] = [];
  for (const row of rows) {
    const id = row.rule_id || "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    unique.push(row);
  }
  return unique;
}

function matchesRule(row: GuidanceRulePickerRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    row.rule_id,
    row.name,
    row.guideline_title,
    row.recommendation_text,
    ...(row.trigger_terms || []),
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function letterFromRule(row: GuidanceRulePickerRow): string {
  const terms = (row.trigger_terms || []).join(", ");
  const rec = row.recommendation_text || terms || row.name || row.rule_id;
  return [
    "Dear colleague,",
    "",
    `Please see this patient. ${rec}`,
    terms ? `Relevant phrases: ${terms}.` : "",
    "",
    "Yours sincerely,",
    "GP",
  ]
    .filter(Boolean)
    .join("\n");
}

function letterFromPhrases(phrases: string[]): string {
  return [
    "Dear colleague,",
    "",
    `Please see this patient. ${phrases.join("; ")}.`,
    "",
    "Yours sincerely,",
    "GP",
  ].join("\n");
}

function caseFromRule(
  rule: GuidanceRulePickerRow | null,
  letter: string,
  gpNote: string,
) {
  return {
    title: rule ? `Rule test: ${rule.name || rule.rule_id}` : "Rule test",
    referral_text: letter,
    plan_id: DEFAULT_LAB_PLAN_ID,
    tags: rule ? [rule.rule_id] : [],
    pmh: [],
    encounters: gpNote
      ? [{ label: "GP consult", text: gpNote, date: "" }]
      : [],
  };
}

function reviewFromCase(
  created: LabCase,
  runId: string,
  status: string,
  letter: string,
  gpNote: string,
  terminal = false,
): RunReviewTarget {
  return {
    title: created.title,
    caseId: created.id,
    labRunId: runId,
    referralText: letter,
    gpNote,
    status,
    terminal: terminal || status === "completed" || status === "failed",
    assessmentCaseId: created.id,
  };
}
