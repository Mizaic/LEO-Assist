/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
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
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";

import AIDraftButton from "../AIDraftButton";
import LogicTreeEditor from "../LogicTreeEditor";
import {
  DUPLICATE_SETS_ALERT,
  STEP_HELPERS,
  STEP_TITLES,
  OR_SYMPTOMS_PREREQUISITE_HINT,
} from "../copy";
import {
  hasOrRootSymptomsOnly,
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

  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
  ) => void;
  onRequestCoach: (nodeId: string, anchor: HTMLElement) => void;
  /** Trigger an empty-state +Add when the tree has no children yet. */
  onAddFirstSymptom: (anchor: HTMLElement) => void;
  onAddFirstDemographic?: () => void;
  onAddFirstObservation?: () => void;
  /** Rule ID used by the AI-draft button. Empty string when unsaved. */
  ruleId?: string;
  /** Called when the AI draft succeeds; replaces the current tree. */
  onAIDraft?: (tree: EditableLogicNode) => void;
  /** Guideline ID for RULE_FIRED rule picker (DI-6AE25829). */
  guidelineId?: string;
}

export default function Step1Who({
  tree,
  selectedNodeId,
  duplicates,
  recommendationText,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  onAddFirstSymptom,
  onAddFirstDemographic,
  onAddFirstObservation,
  ruleId = "",
  onAIDraft,
  guidelineId,
}: Props) {
  const treeIsEmpty = isTreeVisuallyEmpty(tree);

  const { wrappedOnUpdate, confirmDialogs } = useConfirmEdits({
    tree,
    onUpdate,
  });

  const showStructureWarning = tree && hasOrRootWithPrerequisites(tree);
  const showPrerequisiteHint = tree && hasOrRootSymptomsOnly(tree);

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

      {showPrerequisiteHint && (
        <Alert
          severity="info"
          role="status"
          aria-label={OR_SYMPTOMS_PREREQUISITE_HINT.ariaLabel}
          sx={{ py: 0.75 }}
        >
          {OR_SYMPTOMS_PREREQUISITE_HINT.lead}{" "}
          {OR_SYMPTOMS_PREREQUISITE_HINT.action}{" "}
          <strong>{OR_SYMPTOMS_PREREQUISITE_HINT.actionStrong}</strong>{" "}
          {OR_SYMPTOMS_PREREQUISITE_HINT.tail}
        </Alert>
      )}

      {recommendationText && (
        <Box
          sx={{
            p: 1.5,
            borderLeft: "4px solid",
            borderColor: "primary.main",
            bgcolor: "primary.50",
            borderRadius: "0 8px 8px 0",
          }}
        >
          <Typography
            variant="caption"
            sx={{ fontWeight: 700, color: "primary.dark", display: "block", mb: 0.5, textTransform: "uppercase", letterSpacing: "0.04em", fontSize: "0.68rem" }}
          >
            NICE recommendation
          </Typography>
          <Typography
            variant="body2"
            sx={{ fontStyle: "italic", lineHeight: 1.6, color: "text.primary" }}
          >
            {recommendationText}
          </Typography>
        </Box>
      )}

      {treeIsEmpty ? (
        <EmptyTreeState
          onAddFirstSymptom={onAddFirstSymptom}
          onAddFirstDemographic={onAddFirstDemographic}
          onAddFirstObservation={onAddFirstObservation}
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
              guidelineId={guidelineId}
              currentRuleId={ruleId || undefined}
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

const emptyAddBtnSx = {
  borderRadius: 999,
  textTransform: "none",
  fontWeight: 500,
  px: 2,
  border: "1.5px dashed",
  borderColor: "divider",
  color: "text.secondary",
  bgcolor: "transparent",
  "&:hover": { borderColor: "primary.main", color: "primary.main", bgcolor: "primary.50" },
} as const;

function EmptyTreeState({
  onAddFirstSymptom,
  onAddFirstDemographic,
  onAddFirstObservation,
  ruleId,
  onAIDraft,
}: {
  onAddFirstSymptom: (anchor: HTMLElement) => void;
  onAddFirstDemographic?: () => void;
  onAddFirstObservation?: () => void;
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
      <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5, color: "text.primary" }}>
        What does this rule apply to?
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.5, mb: 2.5 }}>
        Start with a symptom, procedure, situation, patient detail (like age or sex), or a lab result.
      </Typography>

      <Stack direction="row" spacing={1} justifyContent="center" flexWrap="wrap" sx={{ rowGap: 1, mb: 2 }}>
        <Button
          variant="outlined"
          startIcon={<AddRoundedIcon fontSize="small" />}
          onClick={(e) => onAddFirstSymptom(e.currentTarget)}
          aria-label="Add the first symptom, sign, procedure, or situation to this rule"
          sx={emptyAddBtnSx}
        >
          Symptom, procedure, or situation
        </Button>
        {onAddFirstDemographic && (
          <Button
            variant="outlined"
            startIcon={<AddRoundedIcon fontSize="small" />}
            onClick={onAddFirstDemographic}
            aria-label="Add a patient detail such as age or sex"
            sx={emptyAddBtnSx}
          >
            Patient detail (age, sex&hellip;)
          </Button>
        )}
        {onAddFirstObservation && (
          <Button
            variant="outlined"
            startIcon={<AddRoundedIcon fontSize="small" />}
            onClick={onAddFirstObservation}
            aria-label="Add a lab value or measurement"
            sx={emptyAddBtnSx}
          >
            Lab value or reading
          </Button>
        )}
      </Stack>

      {ruleId && onAIDraft && (
        <>
          <Divider sx={{ my: 2 }}>or let AI draft it</Divider>
          <AIDraftButton ruleId={ruleId} onDraft={onAIDraft} variant="primary-cta" />
        </>
      )}
    </Box>
  );
}
