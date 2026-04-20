/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-1B7E7255
 *   Also implements: DO-F8631A82
 *   DI: DI-1B8AC856, DI-EA432FDA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1B7E7255")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TermSearch from "@/components/TermSearch";
import type { ReviewItem } from "@/components/operations/ReviewCard";
import type { AskLeoSmartResult, TermSearchResult } from "@/lib/types";
import CaseCard from "./CaseCard";
import CodingReviewCasesModalTitle from "./CodingReviewCasesModalTitle";
import {
  isClinicalSafetyWarning,
  jsonFetch,
  type CaseRecord,
  type SiblingEntity,
} from "./codingReviewUtils";
import { CODING_REVIEW_INTRO } from "./codingReviewCopy";

export { CODING_REVIEW_INTRO };

interface Props {
  item: ReviewItem;
  open: boolean;
  onClose: () => void;
  onAllResolved: () => void;
  initialCases?: CaseRecord[];
  prefilledResults?: Record<string, AskLeoSmartResult>;
}

export default function CodingReviewCasesModal({
  item,
  open,
  onClose,
  onAllResolved,
  initialCases,
  prefilledResults,
}: Props) {
  const [cases, setCases] = useState<CaseRecord[]>(initialCases ?? []);
  const [loading, setLoading] = useState(!initialCases);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [singleTarget, setSingleTarget] = useState<CaseRecord | null>(null);
  const [siblings, setSiblings] = useState<Record<string, SiblingEntity[]>>(
    {},
  );

  const rawLabel = item.entityLabel.replace(/_/g, " ") || "";
  const [labelOverride, setLabelOverride] = useState(rawLabel);
  const [labelMenuAnchor, setLabelMenuAnchor] =
    useState<null | HTMLElement>(null);
  const [savingLabel, setSavingLabel] = useState(false);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(item.entityText);
      const data = await jsonFetch<{ items: CaseRecord[] }>(
        `/api/training/coding-review/queue?entity_text=${encoded}&page_size=200`,
      );
      setCases(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load cases");
    } finally {
      setLoading(false);
    }
  }, [item.entityText]);

  useEffect(() => {
    if (open && !initialCases) loadCases();
  }, [open, loadCases, initialCases]);

  useEffect(() => {
    if (cases.length === 0) return;
    const labelIds = cases
      .map((c) => c.label_id)
      .filter(Boolean) as string[];
    if (labelIds.length === 0) return;

    const unique = [...new Set(labelIds)];
    jsonFetch<{ siblings: Record<string, SiblingEntity[]> }>(
      "/api/training/coding-review/encounter-siblings",
      { method: "POST", body: JSON.stringify({ label_ids: unique }) },
    )
      .then((res) => setSiblings(res.siblings))
      .catch(() => {
        // non-critical -- context panel just won't appear
      });
  }, [cases]);

  const handleCorrectLabel = useCallback(
    async (newLabel: string) => {
      setLabelMenuAnchor(null);
      if (newLabel === labelOverride) return;
      setLabelOverride(newLabel);
      setSavingLabel(true);
      try {
        await jsonFetch("/api/training/coding-review/entity-label", {
          method: "PATCH",
          body: JSON.stringify({
            entity_text: item.entityText,
            entity_label: newLabel.replace(/ /g, "_"),
            corrected_by: "operations_ui",
          }),
        });
      } catch {
        // Non-fatal: the UI override is already applied for this session.
      } finally {
        setSavingLabel(false);
      }
    },
    [labelOverride, item.entityText],
  );

  const [casesInitialized, setCasesInitialized] = useState(
    initialCases !== undefined && initialCases.length > 0,
  );

  useEffect(() => {
    if (cases.length > 0) setCasesInitialized(true);
  }, [cases.length]);

  useEffect(() => {
    if (casesInitialized && cases.length === 0 && !loading) {
      onAllResolved();
    }
  }, [casesInitialized, cases.length, loading, onAllResolved]);

  const removeCase = useCallback((reviewId: string) => {
    setCases((prev) => prev.filter((c) => c.review_id !== reviewId));
  }, []);

  const handleSingleResolve = useCallback(
    async (
      caseRecord: CaseRecord,
      result: TermSearchResult,
      assertion = "present",
    ) => {
      setResolvingId(caseRecord.review_id);
      setSingleTarget(null);
      try {
        await jsonFetch(
          `/api/training/coding-review/${caseRecord.review_id}/resolve`,
          {
            method: "POST",
            body: JSON.stringify({
              resolved_concept_id: result.snomed_concept_id,
              resolved_term: result.term,
              reviewer: "operations_ui",
              resolved_assertion: assertion,
            }),
          },
        );
        removeCase(caseRecord.review_id);
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not save. Please try again.",
        );
      } finally {
        setResolvingId(null);
      }
    },
    [removeCase],
  );

  const handleBatchResolve = useCallback(
    async (result: TermSearchResult) => {
      setBatchOpen(false);
      setResolvingId("__batch__");
      try {
        await jsonFetch("/api/training/coding-review/batch-resolve", {
          method: "POST",
          body: JSON.stringify({
            entity_text: item.entityText,
            entity_label: item.entityLabel,
            resolved_concept_id: result.snomed_concept_id,
            resolved_term: result.term,
            reviewer: "operations_ui",
            resolved_assertion: item.assertion ?? "present",
          }),
        });
        onAllResolved();
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not save. Please try again.",
        );
      } finally {
        setResolvingId(null);
      }
    },
    [item.entityText, item.entityLabel, item.assertion, onAllResolved],
  );

  const hintTags = labelOverride ? [labelOverride] : undefined;
  const isBatchBusy = resolvingId === "__batch__";
  const isAcceptAllBusy = resolvingId === "__accept_all__";

  const bulkAcceptable = cases.filter((c) => {
    if (c.assertion && c.assertion !== "present") return false;
    if (prefilledResults?.[c.review_id]?.assertion_warning) return false;
    return true;
  });

  const confidentCount = prefilledResults
    ? bulkAcceptable.filter(
        (c) => prefilledResults[c.review_id]?.matched_candidate,
      ).length
    : 0;

  const warningCount = prefilledResults
    ? cases.filter(
        (c) => prefilledResults[c.review_id]?.assertion_warning,
      ).length
    : 0;

  const safetyCount = prefilledResults
    ? cases.filter((c) =>
        isClinicalSafetyWarning(
          prefilledResults[c.review_id]?.assertion_warning,
        ),
      ).length
    : 0;

  const handleAcceptAll = useCallback(async () => {
    if (!prefilledResults) return;
    setResolvingId("__accept_all__");
    setError(null);
    const toResolve = bulkAcceptable.filter(
      (c) => prefilledResults[c.review_id]?.matched_candidate,
    );
    let remaining = [...cases];
    for (const c of toResolve) {
      const leoResult = prefilledResults[c.review_id]!;
      const match = leoResult.matched_candidate!;
      try {
        await jsonFetch(
          `/api/training/coding-review/${c.review_id}/resolve`,
          {
            method: "POST",
            body: JSON.stringify({
              resolved_concept_id: match.snomed_concept_id,
              resolved_term: match.term,
              reviewer: "operations_ui",
              resolved_assertion: leoResult.assertion ?? "present",
            }),
          },
        );
        remaining = remaining.filter((r) => r.review_id !== c.review_id);
        setCases([...remaining]);
      } catch {
        // Leave failed cases in the list for manual review.
      }
    }
    setResolvingId(null);
    if (remaining.length === 0) onAllResolved();
  }, [cases, bulkAcceptable, prefilledResults, onAllResolved]);

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        maxWidth="md"
        fullWidth
        scroll="paper"
      >
        <DialogTitle>
          <CodingReviewCasesModalTitle
            entityText={item.entityText}
            caseCount={cases.length}
            labelOverride={labelOverride}
            rawLabel={rawLabel}
            savingLabel={savingLabel}
            labelMenuAnchor={labelMenuAnchor}
            onOpenLabelMenu={setLabelMenuAnchor}
            onCloseLabelMenu={() => setLabelMenuAnchor(null)}
            onCorrectLabel={handleCorrectLabel}
            confidentCount={confidentCount}
            warningCount={warningCount}
            safetyCount={safetyCount}
            showPrefilledSummary={Boolean(prefilledResults)}
            isAcceptAllBusy={isAcceptAllBusy}
            isBatchBusy={isBatchBusy}
            loading={loading}
            onAcceptAll={handleAcceptAll}
            onBatchOpen={() => setBatchOpen(true)}
          />
        </DialogTitle>

        <DialogContent dividers>
          {error && (
            <Alert
              severity="error"
              onClose={() => setError(null)}
              sx={{ mb: 2 }}
            >
              {error}
            </Alert>
          )}

          {loading && (
            <Box sx={{ textAlign: "center", py: 4 }}>
              <CircularProgress aria-label="Loading" size={28} />
            </Box>
          )}

          {!loading && cases.length === 0 && !error && (
            <Typography
              color="text.secondary"
              sx={{ textAlign: "center", py: 4 }}
            >
              All cases resolved.
            </Typography>
          )}

          <Stack spacing={2}>
            {cases.map((c, idx) => (
              <CaseCard
                key={c.review_id}
                caseRecord={c}
                index={idx + 1}
                total={cases.length}
                busy={
                  resolvingId === c.review_id ||
                  resolvingId === "__accept_all__"
                }
                onCodeThis={() => setSingleTarget(c)}
                onAcceptLeo={(result, assertion) =>
                  handleSingleResolve(c, result, assertion)
                }
                onSuppressed={() => removeCase(c.review_id)}
                hintTags={hintTags}
                initialLeoResult={prefilledResults?.[c.review_id]}
                encounterSiblings={
                  c.label_id ? siblings[c.label_id] : undefined
                }
              />
            ))}
          </Stack>
        </DialogContent>

        <DialogActions>
          <Button onClick={onClose} variant="outlined">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {batchOpen && (
        <TermSearch
          initialQuery={item.entityText}
          hintTags={hintTags}
          entityText={item.entityText}
          entityLabel={item.entityLabel.replace(/_/g, " ")}
          initialEvidence={item.sampleEncounterText}
          onSelect={handleBatchResolve}
          onClose={() => setBatchOpen(false)}
          onCorrection={() => {}}
        />
      )}

      {singleTarget && (
        <TermSearch
          initialQuery={singleTarget.entity_text}
          hintTags={hintTags}
          entityText={singleTarget.entity_text}
          entityLabel={singleTarget.entity_label.replace(/_/g, " ")}
          initialEvidence={singleTarget.encounter_text}
          onSelect={(r) => handleSingleResolve(singleTarget, r)}
          onClose={() => setSingleTarget(null)}
          onCorrection={() => {}}
        />
      )}
    </>
  );
}
