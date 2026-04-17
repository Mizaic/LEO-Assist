"use client";

/**
 * Centred dialog for editing an AI-generated guidance rule before approval.
 *
 * Layout:
 *   - Top: editable rule name + recommended-action dropdown.
 *   - Below: two-column body. Left = LogicTreeEditor (the editable tree).
 *            Right = ConceptSearchPanel (SNOMED search bound to the focused
 *            CONCEPT chip or the focused group's "Add concept" action).
 *   - Bottom: required reason field + Save / Cancel buttons.
 *
 * Saving POSTs to /api/guidance/rules/review/{id}/decision with
 * ``{ action: "edit", reason, updates: { name, strength, logic_tree } }``.
 * The backend writes a new versioned rule and returns the new rule_id.
 */

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import FullscreenExitIcon from "@mui/icons-material/FullscreenExit";
import SearchIcon from "@mui/icons-material/Search";

import ActionPanel from "./ActionPanel";
import ConceptCoachPopover from "./ConceptCoachPopover";
import ConceptSearchPanel from "./ConceptSearchPanel";
import LogicTreeEditor from "./LogicTreeEditor";
import SummaryCard from "./SummaryCard";
import TestPatientsPanel from "./TestPatientsPanel";
import { GROUP_KIND_SHORT, STRENGTH_LABELS, friendlyTerm } from "./copy";
import {
  applyUpdate,
  assignNodeIds,
  findValidationError,
  stripNodeIds,
} from "./treeOps";
import { findDuplicateConceptGroups } from "./namedSets";
import { treeToSentence } from "./treeToSentence";
import { detectVaguePhrase } from "./vaguePhrases";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "./types";

export interface EditableRule {
  rule_id: string;
  name?: string;
  strength?: string;
  guideline_id?: string;
  chapter_title?: string;
  recommendation_text?: string;
  logic_tree?: unknown;
  /** Recommended SNOMED procedure that fires when the rule matches.
   *  Surfaced from the API's actionJson; null when uncoded. */
  action?: LogicCriterion | null;
}

interface Props {
  rule: EditableRule | null;
  open: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (payload: {
    name: string;
    strength: string;
    logic_tree: Record<string, unknown>;
    reason: string;
    /** Only set when the reviewer changed the action SNOMED concept;
     *  omitting it preserves the predecessor's actionJson server-side. */
    action?: LogicCriterion;
  }) => void;
}

const STRENGTH_OPTIONS = STRENGTH_LABELS;

interface SearchTarget {
  mode: "replace" | "add" | "replace_action" | "idle";
  parentNodeId: string | null;
  nodeId: string | null;
  initialQuery: string;
  focusLabel: string | null;
}

const IDLE_TARGET: SearchTarget = {
  mode: "idle",
  parentNodeId: null,
  nodeId: null,
  initialQuery: "",
  focusLabel: null,
};

export default function EditRuleDialog({
  rule,
  open,
  saving,
  onClose,
  onSave,
}: Props) {
  const [tree, setTree] = useState<EditableLogicNode | null>(null);
  const [name, setName] = useState("");
  const [strength, setStrength] = useState("unspecified");
  const [reason, setReason] = useState("");
  const [searchTarget, setSearchTarget] = useState<SearchTarget>(IDLE_TARGET);
  const [showRecommendation, setShowRecommendation] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [searchPanelPinned, setSearchPanelPinned] = useState(false);
  const [coach, setCoach] = useState<{
    nodeId: string;
    anchor: HTMLElement;
  } | null>(null);
  // The SNOMED-coded recommended procedure (action) -- separate from the
  // logic tree because it is what the system *suggests* when the rule
  // matches, not what the patient must have. ``actionDirty`` lets us
  // omit ``action`` from the save payload when the reviewer never
  // touched it, so the server preserves the predecessor's actionJson
  // unchanged (DI-LEO-AI-170 safety constraint).
  const [action, setAction] = useState<LogicCriterion | null>(null);
  const [actionDirty, setActionDirty] = useState(false);

  useEffect(() => {
    if (!rule) return;
    const initialTree =
      rule.logic_tree && typeof rule.logic_tree === "object"
        ? assignNodeIds(rule.logic_tree as EditableLogicNode)
        : assignNodeIds({ kind: "AND", children: [] });
    setTree(initialTree);
    setName(rule.name ?? "");
    setStrength(rule.strength || "unspecified");
    setReason("");
    setSearchTarget(IDLE_TARGET);
    setShowRecommendation(false);
    setSearchPanelPinned(false);
    setCoach(null);
    setAction(rule.action ?? null);
    setActionDirty(false);
  }, [rule]);

  const summary = useMemo(() => treeToSentence(tree), [tree]);
  const duplicates = useMemo(() => findDuplicateConceptGroups(tree), [tree]);
  // Hash of the current tree -- used by TestPatientsPanel to auto-replay
  // whenever the reviewer's edits could change which patients match.
  const ruleSignature = useMemo(
    () => (tree ? JSON.stringify(stripNodeIds(tree)) : ""),
    [tree],
  );

  // The right-hand search column is "open" when the user is actively
  // picking a concept OR when they have explicitly pinned it open via
  // the slim rail. Otherwise it collapses to a 56px rail so the tree
  // gets the full dialog width.
  const searchPanelOpen = searchTarget.mode !== "idle" || searchPanelPinned;

  const validationError = useMemo(() => findValidationError(tree), [tree]);
  const canSave = !!tree && !validationError && reason.trim().length >= 3 && !saving;

  function handleUpdate(update: NodeUpdate) {
    setTree((curr) => (curr ? applyUpdate(curr, update) : curr));
    if (update.kind === "remove" && searchTarget.nodeId === update.nodeId) {
      setSearchTarget(IDLE_TARGET);
    }
  }

  function handleSelectNode(nodeId: string) {
    if (!tree) return;
    const focused = findNode(tree, nodeId);
    if (!focused) return;
    if (focused.kind !== "CONCEPT") {
      setSearchTarget(IDLE_TARGET);
      return;
    }
    const friendly = friendlyTerm(focused.criterion?.preferred_term);
    setSearchTarget({
      mode: "replace",
      parentNodeId: null,
      nodeId,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping: ${friendly}`
        : "Pick a symptom or sign for the empty pill",
    });
  }

  function handleRequestAdd(parentNodeId: string) {
    if (!tree) return;
    const parent = findNode(tree, parentNodeId);
    setSearchTarget({
      mode: "add",
      parentNodeId,
      nodeId: null,
      initialQuery: "",
      focusLabel: parent
        ? `Adding to: ${groupLabel(parent.kind)}`
        : "Adding a symptom or sign",
    });
  }

  function handleRequestCoach(nodeId: string, anchor: HTMLElement) {
    setCoach({ nodeId, anchor });
  }

  function handleCoachAddCriteria(
    criteria: LogicCriterion[],
    replaceVague: boolean,
  ) {
    if (!tree || !coach) return;
    const parent = findParent(tree, coach.nodeId);
    if (!parent) return;
    let nextTree: EditableLogicNode | null = tree;
    for (const criterion of criteria) {
      if (!nextTree) break;
      nextTree = applyUpdate(nextTree, {
        kind: "add_concept",
        parentNodeId: parent.node_id,
        criterion,
      });
    }
    if (replaceVague && nextTree) {
      nextTree = applyUpdate(nextTree, { kind: "remove", nodeId: coach.nodeId });
    }
    setTree(nextTree);
    setCoach(null);
    if (replaceVague && searchTarget.nodeId === coach.nodeId) {
      setSearchTarget(IDLE_TARGET);
    }
  }

  function handleCoachSearchMore(topic: string) {
    if (!coach || !tree) return;
    const parent = findParent(tree, coach.nodeId);
    setSearchTarget({
      mode: "add",
      parentNodeId: parent?.node_id ?? null,
      nodeId: null,
      initialQuery: topic,
      focusLabel: `Adding to: ${parent ? groupLabel(parent.kind) : "the rule"}`,
    });
    setSearchPanelPinned(true);
    setCoach(null);
  }

  function handleSelectAction() {
    const friendly = friendlyTerm(action?.preferred_term);
    setSearchTarget({
      mode: "replace_action",
      parentNodeId: null,
      nodeId: null,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping the procedure: ${friendly}`
        : "Pick the procedure the system should suggest",
    });
  }

  function handlePick(criterion: LogicCriterion) {
    if (searchTarget.mode === "replace_action") {
      setAction(criterion);
      setActionDirty(true);
      setSearchTarget(IDLE_TARGET);
      setSearchPanelPinned(false);
      return;
    }
    if (searchTarget.mode === "replace" && searchTarget.nodeId) {
      handleUpdate({ kind: "replace_concept", nodeId: searchTarget.nodeId, criterion });
      setSearchTarget(IDLE_TARGET);
      setSearchPanelPinned(false);
      return;
    }
    if (searchTarget.mode === "add" && searchTarget.parentNodeId) {
      handleUpdate({
        kind: "add_concept",
        parentNodeId: searchTarget.parentNodeId,
        criterion,
      });
    }
  }

  function handleSave() {
    if (!tree || !canSave) return;
    onSave({
      name: name.trim(),
      strength,
      logic_tree: stripNodeIds(tree),
      reason: reason.trim(),
      ...(actionDirty && action ? { action } : {}),
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      fullScreen={fullscreen}
      maxWidth="lg"
      aria-labelledby="edit-rule-dialog-title"
      PaperProps={{
        sx: fullscreen
          ? { display: "flex", flexDirection: "column" }
          : { minHeight: "70vh", display: "flex", flexDirection: "column" },
      }}
    >
      <DialogTitle id="edit-rule-dialog-title" component="div" sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" component="h2" sx={{ fontWeight: 700, fontSize: "1.05rem" }}>
              Change this rule
            </Typography>
            {rule?.chapter_title && (
              <Typography variant="caption" color="text.secondary">
                {rule.guideline_id ? `${rule.guideline_id} - ` : ""}
                {rule.chapter_title}
              </Typography>
            )}
          </Box>
          <Tooltip title={fullscreen ? "Shrink to a window" : "Use the full screen"}>
            <IconButton
              onClick={() => setFullscreen((v) => !v)}
              size="small"
              aria-label={fullscreen ? "Shrink to a window" : "Use the full screen"}
            >
              {fullscreen ? (
                <FullscreenExitIcon fontSize="small" />
              ) : (
                <FullscreenIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
          <IconButton
            onClick={onClose}
            size="small"
            aria-label="Close without saving"
            disabled={saving}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <SummaryCard summary={summary} />
          {duplicates.length > 0 && (
            <Alert
              severity="info"
              role="status"
              aria-label="Repeated symptom set warning"
              sx={{ py: 0.5 }}
            >
              {duplicates.length === 1 ? (
                <>
                  This rule has the <strong>same symptom set</strong> in two
                  places: {duplicates[0].preview.join(", ")}
                  {duplicates[0].preview.length < 3 ? "" : ", ..."}. Keeping
                  duplicates is fine, but you can remove one to keep the rule
                  shorter.
                </>
              ) : (
                <>
                  This rule has <strong>{duplicates.length} repeated symptom
                  sets</strong>. Removing duplicates keeps the rule easier to
                  read.
                </>
              )}
            </Alert>
          )}
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ lineHeight: 1.5 }}
          >
            Click any green pill to swap a symptom. Use the{" "}
            <strong>+ Add</strong> buttons to add more. A yellow lightbulb
            means the term is vague -- click it for clearer suggestions.
          </Typography>

          {rule?.recommendation_text && (
            <Box>
              <Link
                component="button"
                type="button"
                variant="caption"
                onClick={() => setShowRecommendation((v) => !v)}
                sx={{ textTransform: "none" }}
              >
                {showRecommendation
                  ? "Hide the original NICE text"
                  : "Show the original NICE text"}
              </Link>
              {showRecommendation && (
                <Box
                  sx={{
                    mt: 0.5,
                    p: 1.25,
                    borderRadius: 1,
                    bgcolor: "grey.50",
                    border: "1px solid",
                    borderColor: "grey.200",
                  }}
                >
                  <Typography variant="body2" sx={{ fontStyle: "italic", lineHeight: 1.6 }}>
                    &ldquo;{rule.recommendation_text}&rdquo;
                  </Typography>
                </Box>
              )}
            </Box>
          )}

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <TextField
              size="small"
              label="Short name for this rule"
              helperText="Shown to clinicians in the review queue."
              value={name}
              onChange={(e) => setName(e.target.value)}
              inputProps={{ "aria-label": "Short name for this rule", maxLength: 200 }}
              sx={{ flex: 2 }}
            />
            <Box sx={{ flex: 1, minWidth: 220 }}>
              <Typography
                variant="caption"
                component="label"
                htmlFor="edit-rule-strength"
                sx={{ display: "block", color: "text.secondary", mb: 0.25, ml: 0.5 }}
              >
                What should the system suggest?
              </Typography>
              <Select
                id="edit-rule-strength"
                size="small"
                fullWidth
                value={strength}
                onChange={(e) => setStrength(String(e.target.value))}
                inputProps={{ "aria-label": "What should the system suggest" }}
              >
                {STRENGTH_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </Box>
          </Stack>

          {validationError && (
            <Alert severity="warning" sx={{ py: 0.5 }} role="status">
              {validationError}
            </Alert>
          )}

          {rule?.rule_id && (
            <TestPatientsPanel
              ruleId={rule.rule_id}
              guidelineId={rule.guideline_id}
              ruleSignature={ruleSignature}
              ruleName={name || rule.name}
              recommendationText={rule.recommendation_text}
              draftRule={
                tree
                  ? {
                      rule_id: rule.rule_id,
                      name: name || rule.name || "",
                      strength: strength || "unspecified",
                      guideline_id: rule.guideline_id,
                      guideline_title: rule.chapter_title || "",
                      chapter_title: rule.chapter_title,
                      recommendation_verbatim: rule.recommendation_text || "",
                      logic_tree: stripNodeIds(tree),
                      ...(actionDirty && action ? { action } : {}),
                    }
                  : null
              }
            />
          )}

          <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={2}
            alignItems="stretch"
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Stack spacing={1.5}>
                <ActionPanel
                  action={action}
                  isSelected={searchTarget.mode === "replace_action"}
                  onSelect={handleSelectAction}
                />
                {tree && (
                  <LogicTreeEditor
                    root={tree}
                    selectedNodeId={searchTarget.nodeId}
                    onSelect={handleSelectNode}
                    onUpdate={handleUpdate}
                    onRequestAdd={handleRequestAdd}
                    onRequestCoach={handleRequestCoach}
                  />
                )}
              </Stack>
            </Box>
            <Box
              sx={{
                display: { xs: "block", md: "flex" },
                alignItems: "stretch",
                minWidth: 0,
              }}
            >
              <Collapse
                in={searchPanelOpen}
                orientation="horizontal"
                timeout={200}
                unmountOnExit
                sx={{
                  "& .MuiCollapse-wrapperInner": {
                    width: { xs: "100%", md: 380 },
                  },
                }}
              >
                <Box sx={{ width: { xs: "100%", md: 380 }, pl: { md: 1.5 } }}>
                  <ConceptSearchPanel
                    mode={searchTarget.mode === "idle" ? "idle" : searchTarget.mode}
                    focusLabel={searchTarget.focusLabel}
                    initialQuery={searchTarget.initialQuery}
                    onPick={handlePick}
                  />
                </Box>
              </Collapse>
              {!searchPanelOpen && (
                <SearchPanelRail onOpen={() => setSearchPanelPinned(true)} />
              )}
            </Box>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions
        sx={{
          px: 3,
          py: 2,
          position: "sticky",
          bottom: 0,
          bgcolor: "background.paper",
          borderTop: "1px solid",
          borderColor: "divider",
          zIndex: 1,
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flex: 1 }}>
          <TextField
            size="small"
            label="Why are you changing this rule?"
            placeholder="For example: NICE updated the age threshold."
            helperText="At least 3 characters. Saved with the change so others can see why."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            inputProps={{
              "aria-label": "Why are you changing this rule",
              minLength: 3,
            }}
            required
            sx={{ flex: 1 }}
            disabled={saving}
          />
          {saving && <CircularProgress size={18} aria-label="Saving your changes" />}
        </Stack>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!canSave}
          aria-label="Save your changes"
        >
          Save changes
        </Button>
      </DialogActions>
      {coach && tree && (() => {
        const node = findNode(tree, coach.nodeId);
        const term = node?.criterion?.preferred_term ?? "";
        const match = detectVaguePhrase(term);
        if (!match.isVague) return null;
        return (
          <ConceptCoachPopover
            open
            anchorEl={coach.anchor}
            vagueTerm={friendlyTerm(term)}
            match={match}
            onClose={() => setCoach(null)}
            onAddCriteria={handleCoachAddCriteria}
            onSearchMore={handleCoachSearchMore}
          />
        );
      })()}
    </Dialog>
  );
}

/**
 * Slim 56px rail shown when the search panel is collapsed. Click to pin
 * the panel open. Acts as a constant signpost so the reviewer knows the
 * search is one click away even when not in use.
 */
function SearchPanelRail({ onOpen }: { onOpen: () => void }) {
  return (
    <Tooltip title="Open search to pick a clinical term" placement="left">
      <Box
        component="button"
        type="button"
        onClick={onOpen}
        aria-label="Open search to pick a clinical term"
        sx={{
          width: { xs: "100%", md: 56 },
          minHeight: { xs: 48, md: 240 },
          ml: { md: 1 },
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "transparent",
          color: "text.secondary",
          cursor: "pointer",
          py: 1,
          "&:hover": { bgcolor: "action.hover", color: "text.primary" },
        }}
      >
        <SearchIcon fontSize="small" />
        <Typography
          variant="caption"
          sx={{
            writingMode: { md: "vertical-rl" },
            transform: { md: "rotate(180deg)" },
            letterSpacing: 0.5,
          }}
        >
          Search clinical terms
        </Typography>
      </Box>
    </Tooltip>
  );
}

function findNode(node: EditableLogicNode, nodeId: string): EditableLogicNode | null {
  if (node.node_id === nodeId) return node;
  for (const child of node.children ?? []) {
    const hit = findNode(child, nodeId);
    if (hit) return hit;
  }
  return null;
}

function findParent(
  node: EditableLogicNode,
  childId: string,
): EditableLogicNode | null {
  for (const child of node.children ?? []) {
    if (child.node_id === childId) return node;
    const hit = findParent(child, childId);
    if (hit) return hit;
  }
  return null;
}

function groupLabel(kind: string): string {
  return GROUP_KIND_SHORT[kind as keyof typeof GROUP_KIND_SHORT] ?? kind;
}
