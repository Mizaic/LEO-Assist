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
 * RecommendationPickerDialog
 *
 * Opens from "Recommendations" on a guideline row. Shows every chapter
 * and recommendation. The user selects which recs to act on and picks
 * "AI draft" or "Build by hand" per rec.
 *
 * AI draft  -> POST /api/guidance/rules/generate (with recommendation_ids)
 * By hand   -> POST /api/guidance/rules/create-blank, then EditRuleDialog
 * Attach    -> return selected recs via onAttach (Validation Lab)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import {
  allNormativeRecs,
  buildInitialSelection,
  pickAttachRule,
  recHasApprovedRule,
  recHasCompiledRule,
  selectMatchingRecs,
  type RecSelection,
  type SelectionMap,
} from "./recommendationPickerSelection";
import { ChapterSection } from "./RecommendationPickerRows";
import { DialogFooter } from "./RecommendationPickerFooter";
import { RecommendationPickerToolbar } from "./RecommendationPickerToolbar";
import {
  createBlankRule,
  fetchCompiledRuleIds,
  fetchSubgraph,
  pollGenerateJob,
  startGenerateJob,
} from "./recommendationPickerApi";

import EditRuleDialog, { type EditableRule } from "./EditRuleDialog";
import { ruleToEditable } from "./ruleReviewHelpers";
import type { Rule } from "./ruleReviewTypes";

export interface AttachedRecommendation {
  recId: string;
  guidelineCode: string;
  verbatim: string;
  recTitle: string;
  ruleId: string;
  ruleStatus: string;
}

interface Props {
  code: string | null;
  guidelineTitle: string;
  source?: "nice_syndication_api" | "local_guideline";
  onClose: () => void;
  onRulesGenerated: () => void;
  /** When "attach", selected recs are returned via onAttach instead of drafting rules. */
  mode?: "rules" | "attach";
  onAttach?: (recs: AttachedRecommendation[]) => void;
}

// LONG FUNCTION: dialog state machine (load, select, generate, hand-edit queue).
export default function RecommendationPickerDialog({
  code,
  guidelineTitle,
  source = "nice_syndication_api",
  onClose,
  onRulesGenerated,
  mode = "rules",
  onAttach,
}: Props) {
  const attachMode = mode === "attach";
  const [data, setData] = useState<Awaited<
    ReturnType<typeof fetchSubgraph>
  > | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [selection, setSelection] = useState<SelectionMap>({});
  const [compiledRuleIds, setCompiledRuleIds] = useState<Set<string>>(new Set());

  const [generating, setGenerating] = useState(false);
  const [generationDone, setGenerationDone] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const [creatingStub, setCreatingStub] = useState(false);
  const [handQueue, setHandQueue] = useState<string[]>([]);
  const [editRule, setEditRule] = useState<EditableRule | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (pollRef.current) clearTimeout(pollRef.current);
  }, []);

  useEffect(() => {
    if (!code) {
      setData(null);
      setSelection({});
      setGenerationDone(false);
      setCompiledRuleIds(new Set());
      return;
    }
    setLoadingData(true);
    setLoadError(null);
    const loads: Promise<unknown>[] = [
      fetchSubgraph(code, source).then((d) => {
        setData(d);
        setSelection(buildInitialSelection(d.chapters, attachMode));
      }),
    ];
    if (attachMode) {
      loads.push(fetchCompiledRuleIds().then(setCompiledRuleIds));
    }
    Promise.all(loads)
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "Could not load recommendations."),
      )
      .finally(() => setLoadingData(false));
  }, [code, source, attachMode]);

  const updateRec = useCallback((recId: string, patch: Partial<RecSelection>) => {
    setSelection((prev) => ({ ...prev, [recId]: { ...prev[recId], ...patch } }));
  }, []);

  const allRecs = useMemo(() => (data ? allNormativeRecs(data.chapters) : []), [data]);

  const selectedAi = useMemo(
    () =>
      allRecs
        .filter((r) => selection[r.rec_id]?.checked && selection[r.rec_id]?.mode === "ai")
        .map((r) => r.rec_id),
    [allRecs, selection],
  );
  const selectedHand = useMemo(
    () =>
      allRecs
        .filter(
          (r) => selection[r.rec_id]?.checked && selection[r.rec_id]?.mode === "hand",
        )
        .map((r) => r.rec_id),
    [allRecs, selection],
  );

  const approvedCount = useMemo(
    () => allRecs.filter(recHasApprovedRule).length,
    [allRecs],
  );
  const compiledCount = useMemo(
    () => allRecs.filter((r) => recHasCompiledRule(r, compiledRuleIds)).length,
    [allRecs, compiledRuleIds],
  );

  function selectAll() {
    setSelection((prev) => {
      const next = { ...prev };
      for (const r of allRecs) next[r.rec_id] = { ...next[r.rec_id], checked: true };
      return next;
    });
  }

  function selectNone() {
    setSelection((prev) => {
      const next = { ...prev };
      for (const r of allRecs) next[r.rec_id] = { ...next[r.rec_id], checked: false };
      return next;
    });
  }

  function selectAllApproved() {
    setSelection((prev) => selectMatchingRecs(prev, allRecs, recHasApprovedRule));
  }

  function selectAllCompiled() {
    setSelection((prev) =>
      selectMatchingRecs(prev, allRecs, (r) => recHasCompiledRule(r, compiledRuleIds)),
    );
  }

  async function handleGenerate() {
    if (!data || selectedAi.length === 0) return;
    setGenerating(true);
    setGenerationError(null);
    setGenerationDone(false);
    let jobId: string;
    try {
      jobId = await startGenerateJob(data.guideline_id, selectedAi);
    } catch (e) {
      setGenerationError(e instanceof Error ? e.message : "Could not start generation.");
      setGenerating(false);
      return;
    }

    function poll() {
      pollGenerateJob(jobId)
        .then((status) => {
          if (status === "done") {
            setGenerating(false);
            setGenerationDone(true);
            onRulesGenerated();
            return;
          }
          if (status === "error") {
            setGenerating(false);
            setGenerationError("Rule generation failed.");
            return;
          }
          pollRef.current = setTimeout(poll, 5000);
        })
        .catch(() => {
          setGenerating(false);
          setGenerationError("Lost contact with server.");
        });
    }
    pollRef.current = setTimeout(poll, 3000);
  }

  async function openNextHandRec(queue: string[]) {
    const [next, ...rest] = queue;
    if (!next) {
      setHandQueue([]);
      onRulesGenerated();
      return;
    }
    setCreatingStub(true);
    try {
      const rule = await createBlankRule(next);
      setHandQueue(rest);
      setEditRule(ruleToEditable(rule as unknown as Rule));
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Could not create rule stub.");
    } finally {
      setCreatingStub(false);
    }
  }

  function handleBuildHand() {
    if (selectedHand.length === 0) return;
    openNextHandRec(selectedHand);
  }

  async function handleSaveEdit(payload: {
    name: string;
    logic_tree: Record<string, unknown>;
    reason: string;
    actions?: Array<Record<string, unknown>>;
    priority?: "immediate" | "very_urgent" | "2ww" | "urgent" | "routine";
    due_days?: number | null;
    is_default?: boolean;
  }) {
    if (!editRule) return;
    setEditSaving(true);
    setEditError(null);
    try {
      const updates: Record<string, unknown> = {
        name: payload.name,
        logic_tree: payload.logic_tree,
      };
      if (payload.actions !== undefined) updates.actions = payload.actions;
      if (payload.priority !== undefined) {
        updates.priority = payload.priority;
        updates.due_days =
          payload.priority === "routine" ? null : (payload.due_days ?? null);
      }
      if (payload.is_default !== undefined) updates.is_default = payload.is_default;
      const resp = await fetch(`/api/guidance/rules/review/${editRule.rule_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "edit",
          reviewer: "admin",
          reason: payload.reason,
          updates,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setEditRule(null);
      openNextHandRec(handQueue);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Could not save rule.");
    } finally {
      setEditSaving(false);
    }
  }

  function handleCloseEdit() {
    if (editSaving) return;
    setEditRule(null);
    if (handQueue.length > 0) openNextHandRec(handQueue);
    else onRulesGenerated();
  }

  const open = Boolean(code);
  const allNoRules = allRecs.filter((r) => r.rules.length === 0).length;
  const allChecked =
    allRecs.length > 0 && allRecs.every((r) => selection[r.rec_id]?.checked);
  const someChecked = allRecs.some((r) => selection[r.rec_id]?.checked);

  return (
    <>
      <Dialog
        open={open}
        onClose={() => {
          if (!generating && !creatingStub) onClose();
        }}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { maxHeight: "90vh", display: "flex", flexDirection: "column" } }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="h6"
                sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3 }}
              >
                {guidelineTitle || code}
              </Typography>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 0.25, fontSize: "0.8rem" }}
              >
                {attachMode
                  ? "Select recommendations to attach to this test scenario"
                  : "Select recommendations to create rules for"}
              </Typography>
            </Box>
            <IconButton
              size="small"
              onClick={onClose}
              disabled={generating || creatingStub}
              aria-label="Close recommendation picker"
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </DialogTitle>

        <Divider />

        <DialogContent sx={{ flex: 1, overflowY: "auto", p: 2 }}>
          {loadingData && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          )}
          {loadError && <Alert severity="error">{loadError}</Alert>}
          {editError && (
            <Alert severity="error" sx={{ mb: 1 }} onClose={() => setEditError(null)}>
              {editError}
            </Alert>
          )}

          {data && !loadingData && (
            <>
              <RecommendationPickerToolbar
                attachMode={attachMode}
                allChecked={allChecked}
                someChecked={someChecked}
                allNoRules={allNoRules}
                approvedCount={approvedCount}
                compiledCount={compiledCount}
                onToggleAll={(checked) => (checked ? selectAll() : selectNone())}
                onSelectApproved={selectAllApproved}
                onSelectCompiled={selectAllCompiled}
              />

              {data.chapters.map((ch) => (
                <ChapterSection
                  key={ch.chapter_id}
                  chapter={ch}
                  selection={selection}
                  onChangeRec={updateRec}
                  attachMode={attachMode}
                  compiledRuleIds={compiledRuleIds}
                />
              ))}
            </>
          )}
        </DialogContent>

        {data && !loadingData && (
          <DialogFooter
            aiCount={selectedAi.length}
            handCount={selectedHand.length}
            generating={generating}
            creatingStub={creatingStub}
            generationDone={generationDone}
            generationError={generationError}
            onGenerate={handleGenerate}
            onBuildHand={handleBuildHand}
            onClose={onClose}
            attachMode={attachMode}
            attachCount={allRecs.filter((r) => selection[r.rec_id]?.checked).length}
            onAttach={() => {
              if (!onAttach || !code) return;
              const attached: AttachedRecommendation[] = allRecs
                .filter((r) => selection[r.rec_id]?.checked)
                .map((r) => {
                  const chosen = pickAttachRule(r.rules);
                  return {
                    recId: r.rec_id,
                    guidelineCode: code,
                    verbatim: r.verbatim || "",
                    recTitle: r.rec_title || "",
                    ruleId: chosen?.rule_id || "",
                    ruleStatus: chosen?.status || "",
                  };
                });
              onAttach(attached);
            }}
          />
        )}
      </Dialog>

      <EditRuleDialog
        rule={editRule}
        open={!!editRule}
        saving={editSaving}
        saveError={editError}
        onClose={handleCloseEdit}
        onSave={handleSaveEdit}
      />
    </>
  );
}
