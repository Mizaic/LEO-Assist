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
 * Step 1 -- "Who is this rule about?"
 *
 * Hosts the editable logic tree, the duplicate-set alert, the NICE
 * source toggle, and (when the tree is empty) a friendly empty-state
 * CTA.
 *
 * The LogicTreeEditor is mounted directly -- no Accordion or BlockEditor
 * wrapper. Every rule uses the consumer-grade operator-tree builder.
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";

import AIDraftButton from "../AIDraftButton";
import LogicTreeEditor from "../LogicTreeEditor";
import {
  DUPLICATE_SETS_ALERT,
  STEP_HELPERS,
  STEP_TITLES,
} from "../copy";
import {
  hasOrRootWithPrerequisites,
  isTreeVisuallyEmpty,
  promoteOrPrerequisites,
} from "../treeOps";
import { useConfirmEdits } from "../useConfirmEdits";
import type {
  EditableLogicNode,
  NodeUpdate,
} from "../types";

interface DuplicateSet {
  preview: string[];
}

interface Props {
  tree: EditableLogicNode | null;
  selectedNodeId: string | null;
  duplicates: DuplicateSet[];
  recommendationText?: string;
  showRecommendation: boolean;
  onToggleRecommendation: () => void;

  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
  ) => void;
  onRequestCoach: (nodeId: string, anchor: HTMLElement) => void;
  /** Trigger an empty-state +Add when the tree has no children yet. */
  onAddFirstSymptom: (anchor: HTMLElement) => void;
  /** Rule ID used by the AI-draft button. Empty string when unsaved. */
  ruleId?: string;
  /** Called when the AI draft succeeds; replaces the current tree. */
  onAIDraft?: (tree: EditableLogicNode) => void;
}

export default function Step1Who({
  tree,
  selectedNodeId,
  duplicates,
  recommendationText,
  showRecommendation,
  onToggleRecommendation,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  onAddFirstSymptom,
  ruleId = "",
  onAIDraft,
}: Props) {
  const treeIsEmpty = isTreeVisuallyEmpty(tree);

  const { wrappedOnUpdate, confirmDialogs } = useConfirmEdits({
    tree,
    onUpdate,
  });

  const showStructureWarning = tree && hasOrRootWithPrerequisites(tree);

  function handleFixStructure() {
    if (!tree) return;
    const fixed = promoteOrPrerequisites(tree);
    if (fixed !== tree) {
      onUpdate({ kind: "replace_root", node: fixed });
    }
  }

  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <StepHeader />

      {duplicates.length > 0 && (
        <Alert
          severity="info"
          role="status"
          aria-label={DUPLICATE_SETS_ALERT.ariaLabel}
          sx={{ py: 0.5 }}
        >
          {duplicates.length === 1 ? (
            <>
              {DUPLICATE_SETS_ALERT.oneSetLead}{" "}
              <strong>{DUPLICATE_SETS_ALERT.oneSetStrong}</strong>{" "}
              {DUPLICATE_SETS_ALERT.oneSetMid}{" "}
              {duplicates[0].preview.join(", ")}
              {duplicates[0].preview.length < 3 ? "" : ", ..."}.{" "}
              {DUPLICATE_SETS_ALERT.oneSetTail}
            </>
          ) : (
            <>
              {DUPLICATE_SETS_ALERT.manySetLead}{" "}
              <strong>
                {DUPLICATE_SETS_ALERT.manySetStrong(duplicates.length)}
              </strong>
              . {DUPLICATE_SETS_ALERT.manySetTail}
            </>
          )}
        </Alert>
      )}

      {confirmDialogs}

      {showStructureWarning && (
        <Alert
          severity="warning"
          role="status"
          sx={{ py: 0.75 }}
          action={
            <Button
              size="small"
              color="warning"
              variant="outlined"
              onClick={handleFixStructure}
              sx={{ whiteSpace: "nowrap" }}
            >
              Fix structure
            </Button>
          }
        >
          <strong>Age looks like a prerequisite, not a pathway.</strong>{" "}
          Age (or a lab value) should always apply -- it should not be a
          pathway alternative. Click <strong>Fix structure</strong> to move
          it above the pathways.
        </Alert>
      )}

      {recommendationText && (
        <Box>
          <Link
            component="button"
            type="button"
            variant="caption"
            onClick={onToggleRecommendation}
            sx={{ textTransform: "none" }}
          >
            {showRecommendation
              ? "Hide the original NICE text"
              : "Show the original NICE text"}
          </Link>
          {showRecommendation && (
            <Box
              sx={{
                mt: 0.5, p: 1.25, borderRadius: 1,
                bgcolor: "grey.50", border: "1px solid", borderColor: "grey.200",
              }}
            >
              <Typography
                variant="body2"
                sx={{ fontStyle: "italic", lineHeight: 1.6 }}
              >
                &ldquo;{recommendationText}&rdquo;
              </Typography>
            </Box>
          )}
        </Box>
      )}

      {treeIsEmpty ? (
        <EmptyTreeState
          onAddFirstSymptom={onAddFirstSymptom}
          ruleId={ruleId}
          onAIDraft={onAIDraft}
        />
      ) : (
        tree && (
          <Stack spacing={1.5}>
            {ruleId && onAIDraft && (
              <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                <AIDraftButton
                  ruleId={ruleId}
                  onDraft={onAIDraft}
                  variant="secondary"
                />
              </Box>
            )}
            <LogicTreeEditor
              root={tree}
              selectedNodeId={selectedNodeId}
              onSelect={onSelectNode}
              onUpdate={wrappedOnUpdate}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
            />
          </Stack>
        )
      )}
    </Stack>
  );
}

function StepHeader() {
  return (
    <Box>
      <Typography
        variant="h6"
        component="h3"
        sx={{ fontWeight: 700, fontSize: "1.05rem" }}
      >
        {STEP_TITLES.who}
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.5, mt: 0.5 }}
      >
        {STEP_HELPERS.who}
      </Typography>
    </Box>
  );
}

function EmptyTreeState({
  onAddFirstSymptom,
  ruleId,
  onAIDraft,
}: {
  onAddFirstSymptom: (anchor: HTMLElement) => void;
  ruleId?: string;
  onAIDraft?: (tree: EditableLogicNode) => void;
}) {
  return (
    <Box
      role="status"
      aria-label="This rule is empty"
      sx={{
        p: 3, borderRadius: 2,
        border: "1px dashed", borderColor: "divider",
        bgcolor: "grey.50", textAlign: "center",
      }}
    >
      <Typography
        variant="body1"
        sx={{ fontWeight: 600, mb: 0.5, color: "text.primary" }}
      >
        This rule has no symptoms yet.
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.5, mb: 2 }}
      >
        Start by picking the first symptom or sign the patient must have
        for this rule to apply.
      </Typography>
      <Button
        variant="contained"
        startIcon={<AddRoundedIcon fontSize="small" />}
        onClick={(e) => onAddFirstSymptom(e.currentTarget)}
        aria-label="Add the first symptom or sign to this rule"
        sx={{ borderRadius: 999, textTransform: "none", fontWeight: 600, px: 2.5 }}
      >
        Add the first symptom
      </Button>
      {ruleId && onAIDraft && (
        <>
          <Divider sx={{ my: 2 }}>or</Divider>
          <AIDraftButton ruleId={ruleId} onDraft={onAIDraft} variant="primary-cta" />
        </>
      )}
    </Box>
  );
}
