/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-1B7E7255
 *   DI: DI-EA432FDA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1B7E7255")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { AskLeoBusyMark } from "@/components/AskLeoBusyMark";
import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import { ASSERTION_CHIP } from "@/lib/types";
import type { AskLeoSmartResult, TermSearchResult } from "@/lib/types";
import { getTerminologyConfidenceLabel } from "@/lib/terminologyConfidence";
import {
  ASSERTION_OPTIONS,
  extractSuggestedPhrase,
  isClinicalSafetyWarning,
  jsonFetch,
  safetyPulse,
  warningHeadline,
  type CaseRecord,
  type SiblingEntity,
} from "./codingReviewUtils";
import EncounterContextPanel from "./EncounterContextPanel";
import CaseCardLeoResult from "./CaseCardLeoResult";
import CaseCardSuppressForm from "./CaseCardSuppressForm";

type LeoStep = "idle" | "loading" | "done" | "error";

interface Props {
  caseRecord: CaseRecord;
  index: number;
  total: number;
  busy: boolean;
  onCodeThis: () => void;
  onAcceptLeo: (result: TermSearchResult, assertion: string) => void;
  onSuppressed: () => void;
  hintTags?: string[];
  initialLeoResult?: AskLeoSmartResult;
  encounterSiblings?: SiblingEntity[];
}

export default function CaseCard({
  caseRecord,
  index,
  total,
  busy,
  onCodeThis,
  onAcceptLeo,
  onSuppressed,
  initialLeoResult,
  encounterSiblings,
}: Props) {
  const [leoStep, setLeoStep] = useState<LeoStep>(
    initialLeoResult ? "done" : "idle",
  );
  const [leoResult, setLeoResult] = useState<AskLeoSmartResult | null>(
    initialLeoResult ?? null,
  );
  const [leoError, setLeoError] = useState("");

  const [assertionOverride, setAssertionOverride] = useState(
    caseRecord.assertion || "present",
  );
  const [assertionMenuAnchor, setAssertionMenuAnchor] =
    useState<null | HTMLElement>(null);

  const [suppressOpen, setSuppressOpen] = useState(false);
  const [contextPhrase, setContextPhrase] = useState("");
  const [phraseSource, setPhraseSource] = useState<"leo" | "user" | "none">(
    "none",
  );
  const [suppressing, setSuppressing] = useState(false);
  const [suppressError, setSuppressError] = useState("");

  useEffect(() => {
    const a = caseRecord.assertion || "present";
    const warning = initialLeoResult?.assertion_warning;
    if (a === "absent" || Boolean(warning)) {
      setSuppressOpen(true);
      if (warning) {
        const suggested = extractSuggestedPhrase(
          warning,
          caseRecord.entity_text,
          caseRecord.encounter_text,
        );
        if (suggested) {
          setContextPhrase(suggested);
          setPhraseSource("leo");
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!leoResult?.assertion_warning) return;
    setSuppressOpen(true);
    if (!contextPhrase) {
      const suggested = extractSuggestedPhrase(
        leoResult.assertion_warning,
        caseRecord.entity_text,
        caseRecord.encounter_text,
      );
      if (suggested) {
        setContextPhrase(suggested);
        setPhraseSource("leo");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leoResult?.assertion_warning]);

  useEffect(() => {
    if (leoResult?.assertion && leoResult.assertion !== assertionOverride) {
      setAssertionOverride(leoResult.assertion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leoResult?.assertion]);

  const handleSuppress = useCallback(async () => {
    setSuppressing(true);
    setSuppressError("");
    const escaped = contextPhrase
      .trim()
      .replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contextRegex = contextPhrase.trim() ? `(?i)${escaped}` : null;
    try {
      await jsonFetch("/api/training/post-processor-rules", {
        method: "POST",
        body: JSON.stringify({
          action: "suppress",
          match_text: caseRecord.entity_text,
          match_label: caseRecord.entity_label,
          context_regex: contextRegex,
          priority: 50,
          notes: `Created from coding review ${caseRecord.review_id}`,
          created_by: "operations_ui",
          active: true,
        }),
      });
      await jsonFetch(
        `/api/training/coding-review/${caseRecord.review_id}/ignore`,
        {
          method: "POST",
          body: JSON.stringify({ reviewer: "operations_ui" }),
        },
      );
      onSuppressed();
    } catch {
      setSuppressError("Could not create ignore rule. Please try again.");
    } finally {
      setSuppressing(false);
    }
  }, [caseRecord, contextPhrase, onSuppressed]);

  const handleCorrectAssertion = useCallback(
    async (newAssertion: string) => {
      setAssertionMenuAnchor(null);
      if (newAssertion === assertionOverride) return;
      setAssertionOverride(newAssertion);
      if (newAssertion === "absent" || newAssertion === "declined") {
        setSuppressOpen(true);
      }
      try {
        await jsonFetch(
          `/api/training/coding-review/${caseRecord.review_id}/assertion`,
          {
            method: "PATCH",
            body: JSON.stringify({
              assertion: newAssertion,
              corrected_by: "operations_ui",
            }),
          },
        );
      } catch {
        // Non-fatal: the UI already shows the updated assertion for this session.
      }
    },
    [assertionOverride, caseRecord.review_id],
  );

  const handleAskLeo = useCallback(async () => {
    setLeoStep("loading");
    setLeoResult(null);
    setLeoError("");
    try {
      const candidates = await searchTerms(caseRecord.entity_text, 10);
      const res = await askLeoSmart(
        caseRecord.entity_text,
        caseRecord.encounter_text,
        candidates as unknown as Array<Record<string, unknown>>,
        [],
        "small",
        assertionOverride,
      );
      setLeoResult(res);
      setLeoStep("done");
    } catch {
      setLeoError("Ask LEO is not available right now.");
      setLeoStep("error");
    }
  }, [caseRecord.entity_text, caseRecord.encounter_text, assertionOverride]);

  const activeWarning =
    leoResult?.assertion_warning || initialLeoResult?.assertion_warning;
  const warningIsSafety = isClinicalSafetyWarning(activeWarning);
  const leoMatch = leoResult?.matched_candidate ?? null;
  const assertionChip = ASSERTION_CHIP[assertionOverride];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        sx={{ mb: 1 }}
      >
        <Typography variant="caption" color="text.secondary">
          {index} / {total}
        </Typography>
        <Chip label={caseRecord.source} size="small" />
        {caseRecord.snomed_term && (
          <Chip
            label={`Best match: ${caseRecord.snomed_term} (${getTerminologyConfidenceLabel(caseRecord.score)} confidence)`}
            size="small"
            color="warning"
            variant="outlined"
          />
        )}
        <Tooltip title="Click to correct assertion">
          <Chip
            label={assertionChip ? assertionChip.label : "Present"}
            size="small"
            color={assertionChip ? assertionChip.color : "default"}
            variant={assertionChip ? "filled" : "outlined"}
            onClick={(e) => setAssertionMenuAnchor(e.currentTarget)}
            sx={{ cursor: "pointer", ml: "auto !important" }}
          />
        </Tooltip>
        <Menu
          anchorEl={assertionMenuAnchor}
          open={Boolean(assertionMenuAnchor)}
          onClose={() => setAssertionMenuAnchor(null)}
        >
          {ASSERTION_OPTIONS.map((opt) => (
            <MenuItem
              key={opt}
              selected={opt === assertionOverride}
              onClick={() => handleCorrectAssertion(opt)}
            >
              {opt}
            </MenuItem>
          ))}
        </Menu>
      </Stack>

      <Divider sx={{ mb: 1 }} />

      {activeWarning && (
        <Alert
          severity={warningIsSafety ? "error" : "warning"}
          sx={{
            mb: 1.5,
            py: 0.5,
            ...(warningIsSafety && {
              borderLeft: "4px solid",
              borderColor: "error.main",
              animation: `${safetyPulse} 2s ease-in-out infinite`,
            }),
          }}
        >
          <strong>{warningHeadline(activeWarning)}</strong> {activeWarning}
        </Alert>
      )}

      <AssertionContextAlert assertion={assertionOverride} />

      {caseRecord.suggested_label && (
        <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
          <strong>Semantic tag mismatch:</strong> LLM extracted this as &apos;
          {caseRecord.entity_label.replace(/_/g, " ")}&apos;, but the SNOMED
          resolver suggests &apos;
          {caseRecord.suggested_label.replace(/_/g, " ")}&apos;
          {caseRecord.tag_mismatch_delta != null && (
            <>
              {" "}
              (score delta:{" "}
              {(caseRecord.tag_mismatch_delta * 100).toFixed(0)}%)
            </>
          )}
          . Consider correcting the entity type above before coding.
        </Alert>
      )}

      <Typography
        variant="body2"
        sx={{
          fontFamily: "monospace",
          bgcolor: "grey.50",
          p: 1.5,
          borderRadius: 1,
          mb: 2,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {caseRecord.encounter_text}
      </Typography>

      <EncounterContextPanel
        siblings={encounterSiblings}
        currentReviewId={caseRecord.review_id}
      />

      <CaseCardLeoResult
        step={leoStep}
        result={leoResult}
        error={leoError}
      />

      {suppressOpen && (
        <CaseCardSuppressForm
          entityText={caseRecord.entity_text}
          warning={activeWarning}
          warningIsSafety={warningIsSafety}
          contextPhrase={contextPhrase}
          onContextPhraseChange={(v) => {
            setContextPhrase(v);
            setPhraseSource("user");
          }}
          phraseSource={phraseSource}
          requirePhrase={Boolean(activeWarning)}
          suppressing={suppressing}
          suppressError={suppressError}
          onConfirm={handleSuppress}
          onCancel={() => {
            setSuppressOpen(false);
            setSuppressError("");
          }}
        />
      )}

      <Stack direction="row" spacing={1} flexWrap="wrap">
        {leoStep === "done" && leoMatch && !activeWarning ? (
          <>
            <Button
              variant="contained"
              size="small"
              onClick={() =>
                onAcceptLeo(leoMatch, leoResult?.assertion ?? "present")
              }
              disabled={busy || suppressing}
              startIcon={
                busy ? (
                  <CircularProgress
                    aria-label="Loading"
                    size={14}
                    color="inherit"
                  />
                ) : undefined
              }
            >
              {busy ? "Coding..." : "Accept LEO suggestion"}
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={onCodeThis}
              disabled={busy || suppressing}
            >
              Search differently
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outlined"
              size="small"
              onClick={onCodeThis}
              disabled={busy || leoStep === "loading" || suppressing}
              startIcon={
                busy ? (
                  <CircularProgress aria-label="Loading" size={14} />
                ) : undefined
              }
            >
              {busy ? "Coding..." : "Code this record"}
            </Button>
            <Button
              variant="outlined"
              size="small"
              color="secondary"
              onClick={handleAskLeo}
              disabled={busy || suppressing || leoStep === "loading"}
              startIcon={leoStep === "loading" ? <AskLeoBusyMark /> : undefined}
              aria-busy={leoStep === "loading"}
              aria-label={leoStep === "loading" ? "Asking LEO" : "Ask LEO"}
            >
              {leoStep === "loading" ? "" : "Ask LEO"}
            </Button>
          </>
        )}
        {!suppressOpen && (
          <Button
            size="small"
            variant="outlined"
            color="warning"
            onClick={() => setSuppressOpen(true)}
            disabled={busy || suppressing || leoStep === "loading"}
            sx={{ ml: "auto" }}
          >
            Suppress
          </Button>
        )}
      </Stack>
    </Paper>
  );
}

function AssertionContextAlert({ assertion }: { assertion: string }) {
  if (assertion === "absent") {
    return (
      <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
        This finding appears to be negated in the record. Suppressing is
        likely correct.
      </Alert>
    );
  }
  if (assertion === "declined") {
    return (
      <Alert severity="info" sx={{ mb: 1.5, py: 0.5 }}>
        The patient declined this. Code the underlying procedure using its
        normal SNOMED concept -- Ask LEO will suggest the right code and
        mark it as declined. The timeline will then show it was offered but
        not accepted.
      </Alert>
    );
  }
  if (assertion === "planned") {
    return (
      <Alert severity="info" sx={{ mb: 1.5, py: 0.5 }}>
        This procedure was booked or referred for. Check whether it was
        completed before accepting a code.
      </Alert>
    );
  }
  if (assertion === "hypothetical") {
    return (
      <Alert severity="info" sx={{ mb: 1.5, py: 0.5 }}>
        This is a conditional or speculative future event. It has not been
        arranged -- do not code it as completed.
      </Alert>
    );
  }
  return null;
}
