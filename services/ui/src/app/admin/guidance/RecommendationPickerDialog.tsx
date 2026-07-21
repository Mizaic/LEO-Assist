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
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BuildIcon from "@mui/icons-material/Build";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import GavelIcon from "@mui/icons-material/Gavel";
import {
  allNormativeRecs,
  buildInitialSelection,
  type RecMode,
  type RecSelection,
  type SelectionMap,
} from "./recommendationPickerSelection";

import EditRuleDialog, { type EditableRule } from "./EditRuleDialog";
import { ruleToEditable } from "./ruleReviewHelpers";
import type { Rule } from "./ruleReviewTypes";

// -- Types from the subgraph API -------------------------------------------

interface RuleEntry {
  rule_id: string;
  status: string;
  name: string;
}

interface RecEntry {
  rec_id: string;
  rec_title: string;
  verbatim: string;
  is_normative: boolean;
  section_title: string;
  rules: RuleEntry[];
}

interface ChapterEntry {
  chapter_id: string;
  chapter_title: string;
  order: number;
  recommendations: RecEntry[];
}

interface SubgraphData {
  guideline_id: string;
  guideline_title: string;
  chapters: ChapterEntry[];
}

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

// -- Status badge -----------------------------------------------------------

const STATUS_ICON: Record<string, React.ReactNode> = {
  active: <CheckCircleIcon sx={{ fontSize: 13 }} />,
  pending_review: <HourglassEmptyIcon sx={{ fontSize: 13 }} />,
  rejected: <GavelIcon sx={{ fontSize: 13 }} />,
};

const STATUS_COLOR: Record<string, "success" | "warning" | "error" | "default"> = {
  active: "success",
  pending_review: "warning",
  rejected: "error",
};

function RuleStatusChip({ rule }: { rule: RuleEntry }) {
  const color = STATUS_COLOR[rule.status] ?? "default";
  return (
    <Chip
      icon={STATUS_ICON[rule.status] as React.ReactElement}
      label={rule.status.replace("_", " ")}
      size="small"
      color={color}
      variant="outlined"
      sx={{ height: 20, fontSize: "0.68rem", mr: 0.5 }}
    />
  );
}

// -- Single recommendation row ----------------------------------------------

interface RecRowProps {
  rec: RecEntry;
  sel: RecSelection;
  onChange: (patch: Partial<RecSelection>) => void;
  attachMode?: boolean;
}

function RecRow({ rec, sel, onChange, attachMode = false }: RecRowProps) {
  const [expanded, setExpanded] = useState(false);
  const hasRule = rec.rules.length > 0;
  const preview = rec.verbatim ? rec.verbatim.slice(0, 120) : "(no text stored)";

  return (
    <Box sx={{ py: 0.75, borderBottom: "1px solid", borderColor: "grey.100" }}>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <Checkbox
          size="small"
          checked={sel.checked}
          onChange={(e) => onChange({ checked: e.target.checked })}
          sx={{ mt: -0.25, flexShrink: 0 }}
          inputProps={{ "aria-label": `Select recommendation ${rec.rec_title}` }}
        />

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" sx={{ mb: 0.3 }}>
            {rec.rec_title && (
              <Chip
                label={rec.rec_title}
                size="small"
                sx={{ height: 18, fontSize: "0.68rem", fontFamily: "monospace", bgcolor: "grey.100" }}
              />
            )}
            {rec.rules.map((r) => <RuleStatusChip key={r.rule_id} rule={r} />)}
            {!rec.is_normative && (
              <Chip label="cross-ref" size="small" color="warning" sx={{ height: 16, fontSize: "0.62rem" }} />
            )}
          </Stack>

          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <Box
              sx={{ cursor: rec.verbatim ? "pointer" : "default", pt: 0.1, flexShrink: 0 }}
              onClick={() => rec.verbatim && setExpanded((v) => !v)}
            >
              {rec.verbatim
                ? expanded
                  ? <ExpandMoreIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                  : <ChevronRightIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                : <Box sx={{ width: 14 }} />}
            </Box>
            <Typography
              variant="body2"
              sx={{ fontSize: "0.8rem", lineHeight: 1.5, cursor: rec.verbatim ? "pointer" : "default" }}
              onClick={() => rec.verbatim && setExpanded((v) => !v)}
            >
              {expanded ? rec.verbatim : preview}
              {rec.verbatim && rec.verbatim.length > 120 && !expanded ? "..." : ""}
            </Typography>
          </Stack>

          {sel.checked && attachMode && hasRule ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 0.75, display: "block", fontSize: "0.68rem" }}
            >
              Existing rule can score whether the test case should fire
            </Typography>
          ) : null}

          {sel.checked && !attachMode && (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
              <ToggleButtonGroup
                size="small"
                exclusive
                value={sel.mode}
                onChange={(_, v) => v && onChange({ mode: v as RecMode })}
                aria-label="How to create this rule"
              >
                <ToggleButton value="ai" sx={{ py: 0.25, px: 1, fontSize: "0.72rem", textTransform: "none" }}>
                  <AutoAwesomeIcon sx={{ fontSize: 13, mr: 0.5 }} />
                  AI draft
                </ToggleButton>
                <ToggleButton value="hand" sx={{ py: 0.25, px: 1, fontSize: "0.72rem", textTransform: "none" }}>
                  <BuildIcon sx={{ fontSize: 13, mr: 0.5 }} />
                  Build by hand
                </ToggleButton>
              </ToggleButtonGroup>
              {hasRule && (
                <Typography variant="caption" color="warning.main" sx={{ fontSize: "0.68rem" }}>
                  Has existing rule - will add another
                </Typography>
              )}
            </Stack>
          )}
        </Box>
      </Stack>
    </Box>
  );
}

// -- Chapter accordion ------------------------------------------------------

interface ChapterSectionProps {
  chapter: ChapterEntry;
  selection: SelectionMap;
  onChangeRec: (recId: string, patch: Partial<RecSelection>) => void;
  attachMode?: boolean;
}

function ChapterSection({
  chapter,
  selection,
  onChangeRec,
  attachMode = false,
}: ChapterSectionProps) {
  const normative = chapter.recommendations.filter((r) => r.is_normative);
  const [open, setOpen] = useState(true);

  const checkedCount = normative.filter((r) => selection[r.rec_id]?.checked).length;

  return (
    <Box sx={{ mb: 1 }}>
      <Stack
        direction="row" alignItems="center" spacing={0.5}
        sx={{ cursor: "pointer", p: 0.75, borderRadius: 1, bgcolor: "grey.50", "&:hover": { bgcolor: "grey.100" } }}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ExpandMoreIcon fontSize="small" color="primary" /> : <ChevronRightIcon fontSize="small" />}
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, fontSize: "0.82rem" }}>
          {chapter.chapter_title || chapter.chapter_id}
        </Typography>
        <Chip
          label={`${checkedCount}/${normative.length} selected`}
          size="small"
          color={checkedCount > 0 ? "primary" : "default"}
          variant="outlined"
          sx={{ height: 18, fontSize: "0.65rem" }}
        />
      </Stack>

      <Collapse in={open}>
        <Box sx={{ pl: 1, mt: 0.25 }}>
          {normative.length === 0 ? (
            <Typography variant="caption" color="text.disabled" sx={{ pl: 1, py: 0.5, display: "block" }}>
              No normative recommendations in this chapter.
            </Typography>
          ) : (
            normative.map((rec) => (
              <RecRow
                key={rec.rec_id}
                rec={rec}
                sel={selection[rec.rec_id] ?? { checked: false, mode: "ai" }}
                onChange={(patch) => onChangeRec(rec.rec_id, patch)}
                attachMode={attachMode}
              />
            ))
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

// -- API helpers ------------------------------------------------------------

async function fetchSubgraph(
  code: string,
  source: "nice_syndication_api" | "local_guideline",
): Promise<SubgraphData> {
  const base = source === "local_guideline" ? "/api/guidance/local" : "/api/nice";
  const r = await fetch(`${base}/${encodeURIComponent(code)}/subgraph`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function startGenerateJob(guidelineId: string, recIds: string[]): Promise<string> {
  const r = await fetch("/api/guidance/rules/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guideline_id: guidelineId, recommendation_ids: recIds }),
  });
  if (!r.ok) {
    const b = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error((b as { detail?: string }).detail ?? r.statusText);
  }
  return ((await r.json()) as { job_id: string }).job_id;
}

async function pollGenerateJob(jobId: string): Promise<"running" | "done" | "error"> {
  const r = await fetch(`/api/guidance/rules/generate/${jobId}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json() as { status: string };
  return j.status as "running" | "done" | "error";
}

async function createBlankRule(recId: string): Promise<Rule> {
  const r = await fetch("/api/guidance/rules/create-blank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rec_id: recId }),
  });
  if (!r.ok) {
    const b = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error((b as { detail?: string }).detail ?? r.statusText);
  }
  const data = await r.json() as { rule: Rule };
  return data.rule;
}

// -- Dialog footer -----------------------------------------------------------

interface FooterProps {
  aiCount: number;
  handCount: number;
  generating: boolean;
  creatingStub: boolean;
  generationDone: boolean;
  generationError: string | null;
  onGenerate: () => void;
  onBuildHand: () => void;
  onClose: () => void;
  attachMode?: boolean;
  attachCount?: number;
  onAttach?: () => void;
}

function DialogFooter({
  aiCount, handCount, generating, creatingStub,
  generationDone, generationError, onGenerate, onBuildHand, onClose,
  attachMode = false, attachCount = 0, onAttach,
}: FooterProps) {
  const totalSelected = attachMode ? attachCount : aiCount + handCount;
  return (
    <Box
      sx={{
        px: 2.5, py: 1.5, borderTop: "1px solid", borderColor: "divider",
        bgcolor: "background.paper", position: "sticky", bottom: 0, zIndex: 1,
      }}
    >
      {generationError && (
        <Alert severity="error" sx={{ mb: 1, py: 0.3, fontSize: "0.78rem" }}>{generationError}</Alert>
      )}
      {generationDone && !attachMode && (
        <Alert severity="success" sx={{ mb: 1, py: 0.3, fontSize: "0.78rem" }}>
          AI drafts generated. Rules are in the review queue.
        </Alert>
      )}
      {generating && (
        <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />
      )}
      <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between">
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
          {totalSelected === 0 ? "No recommendations selected" : `${totalSelected} selected`}
          {!attachMode && aiCount > 0 && ` · ${aiCount} AI draft`}
          {!attachMode && handCount > 0 && ` · ${handCount} by hand`}
        </Typography>

        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" onClick={onClose}>
            {generationDone ? "Close" : "Cancel"}
          </Button>
          {attachMode ? (
            <Button
              variant="contained"
              size="small"
              color="primary"
              onClick={onAttach}
              disabled={attachCount === 0}
            >
              Attach selected ({attachCount})
            </Button>
          ) : null}
          {!attachMode && handCount > 0 && (
            <Button
              variant="outlined" size="small" color="primary"
              startIcon={creatingStub ? <CircularProgress size={13} color="inherit" /> : <BuildIcon sx={{ fontSize: 14 }} />}
              onClick={onBuildHand}
              disabled={creatingStub || generating}
            >
              Build by hand ({handCount})
            </Button>
          )}
          {!attachMode && aiCount > 0 && (
            <Button
              variant="contained" size="small" color="primary"
              startIcon={generating ? <CircularProgress size={13} color="inherit" /> : <AutoAwesomeIcon sx={{ fontSize: 14 }} />}
              onClick={onGenerate}
              disabled={generating || creatingStub}
            >
              {generating ? "Generating..." : `Generate AI drafts (${aiCount})`}
            </Button>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}

// -- Main dialog ------------------------------------------------------------

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
  const [data, setData] = useState<SubgraphData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [selection, setSelection] = useState<SelectionMap>({});

  const [generating, setGenerating] = useState(false);
  const [generationDone, setGenerationDone] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const [creatingStub, setCreatingStub] = useState(false);
  const [handQueue, setHandQueue] = useState<string[]>([]);
  const [editRule, setEditRule] = useState<EditableRule | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  useEffect(() => {
    if (!code) { setData(null); setSelection({}); setGenerationDone(false); return; }
    setLoadingData(true);
    setLoadError(null);
      fetchSubgraph(code, source)
      .then((d) => {
        setData(d);
        setSelection(buildInitialSelection(d.chapters, attachMode));
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load recommendations."))
      .finally(() => setLoadingData(false));
  }, [code, source, attachMode]);

  const updateRec = useCallback((recId: string, patch: Partial<RecSelection>) => {
    setSelection((prev) => ({ ...prev, [recId]: { ...prev[recId], ...patch } }));
  }, []);

  const allRecs = useMemo(() => (data ? allNormativeRecs(data.chapters) : []), [data]);

  const selectedAi = useMemo(
    () => allRecs.filter((r) => selection[r.rec_id]?.checked && selection[r.rec_id]?.mode === "ai").map((r) => r.rec_id),
    [allRecs, selection],
  );
  const selectedHand = useMemo(
    () => allRecs.filter((r) => selection[r.rec_id]?.checked && selection[r.rec_id]?.mode === "hand").map((r) => r.rec_id),
    [allRecs, selection],
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
      pollGenerateJob(jobId).then((status) => {
        if (status === "done") { setGenerating(false); setGenerationDone(true); onRulesGenerated(); return; }
        if (status === "error") { setGenerating(false); setGenerationError("Rule generation failed."); return; }
        pollRef.current = setTimeout(poll, 5000);
      }).catch(() => {
        setGenerating(false);
        setGenerationError("Lost contact with server.");
      });
    }
    pollRef.current = setTimeout(poll, 3000);
  }

  async function openNextHandRec(queue: string[]) {
    const [next, ...rest] = queue;
    if (!next) { setHandQueue([]); onRulesGenerated(); return; }
    setCreatingStub(true);
    try {
      const rule = await createBlankRule(next);
      setHandQueue(rest);
      setEditRule(ruleToEditable(rule as unknown as import("./ruleReviewTypes").Rule));
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
    name: string; strength: string; logic_tree: Record<string, unknown>; reason: string;
  }) {
    if (!editRule) return;
    setEditSaving(true);
    setEditError(null);
    try {
      const resp = await fetch(`/api/guidance/rules/review/${editRule.rule_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "edit", reviewer: "admin", reason: payload.reason, updates: {
          name: payload.name, strength: payload.strength, logic_tree: payload.logic_tree,
        }}),
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

  return (
    <>
      <Dialog
        open={open}
        onClose={() => { if (!generating && !creatingStub) onClose(); }}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { maxHeight: "90vh", display: "flex", flexDirection: "column" } }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3 }}>
                {guidelineTitle || code}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, fontSize: "0.8rem" }}>
                {attachMode
                  ? "Select recommendations to attach to this test scenario"
                  : "Select recommendations to create rules for"}
              </Typography>
            </Box>
            <IconButton size="small" onClick={onClose} disabled={generating || creatingStub}
              aria-label="Close recommendation picker">
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
            <Alert severity="error" sx={{ mb: 1 }} onClose={() => setEditError(null)}>{editError}</Alert>
          )}

          {data && !loadingData && (
            <>
              {/* Quick-select toolbar */}
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={allRecs.length > 0 && allRecs.every((r) => selection[r.rec_id]?.checked)}
                      indeterminate={
                        allRecs.some((r) => selection[r.rec_id]?.checked) &&
                        !allRecs.every((r) => selection[r.rec_id]?.checked)
                      }
                      onChange={(e) => (e.target.checked ? selectAll() : selectNone())}
                    />
                  }
                  label={
                    <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
                      All recommendations
                    </Typography>
                  }
                />
                {!attachMode ? (
                  <Typography variant="caption" color="text.secondary">
                    {allNoRules} without rules
                  </Typography>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    Start with none selected — tick the ones to test
                  </Typography>
                )}
              </Stack>

              {data.chapters.map((ch) => (
                <ChapterSection
                  key={ch.chapter_id}
                  chapter={ch}
                  selection={selection}
                  onChangeRec={updateRec}
                  attachMode={attachMode}
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
                  const active = r.rules.find((rule) => rule.status === "active");
                  const first = r.rules[0];
                  return {
                    recId: r.rec_id,
                    guidelineCode: code,
                    verbatim: r.verbatim || "",
                    recTitle: r.rec_title || "",
                    ruleId: (active || first)?.rule_id || "",
                    ruleStatus: (active || first)?.status || "",
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
        onClose={handleCloseEdit}
        onSave={handleSaveEdit}
      />
    </>
  );
}
