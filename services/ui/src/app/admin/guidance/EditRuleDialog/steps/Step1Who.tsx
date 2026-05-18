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
 * Search is no longer rendered as a sibling column. Instead the
 * parent dialog opens a chip-anchored ChipSearchPopover next to the
 * chip / +Add button the reviewer just clicked. This step component
 * is therefore purely about showing the rule.
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  R-LEO-AI-509 (v2), VT-LEO-AI-511 (v2).
 */

import { useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import LogicTreeEditor from "../LogicTreeEditor";
import SentenceCanvas, { type SandboxImpactBadge } from "../SentenceCanvas";
import {
  CANVAS_CARDS,
  DUPLICATE_SETS_ALERT,
  STEP_HELPERS,
  STEP_TITLES,
} from "../copy";
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
  /** Phase 4 sandbox impact badge surfaced on each canvas card. */
  sandboxBadge?: SandboxImpactBadge;
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
  sandboxBadge,
}: Props) {
  const treeIsEmpty =
    !tree ||
    !Array.isArray(tree.children) ||
    tree.children.length === 0;

  const { wrappedOnUpdate, confirmDialogs } = useConfirmEdits({
    tree,
    onUpdate,
  });

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
                mt: 0.5,
                p: 1.25,
                borderRadius: 1,
                bgcolor: "grey.50",
                border: "1px solid",
                borderColor: "grey.200",
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
        <EmptyTreeState onAddFirstSymptom={onAddFirstSymptom} />
      ) : (
        tree && (
          <CanvasAndAdvanced
            tree={tree}
            selectedNodeId={selectedNodeId}
            onSelectNode={onSelectNode}
            onUpdate={wrappedOnUpdate}
            onRequestAdd={onRequestAdd}
            onRequestCoach={onRequestCoach}
            sandboxBadge={sandboxBadge}
          />
        )
      )}
    </Stack>
  );
}

/**
 * Phase 3 layout: the SentenceCanvas is the primary editing surface.
 * The operator-tree editor is demoted to an Advanced-view Accordion
 * directly underneath; first-time reviewers never see it but power
 * users can expand it to access kind selectors, deep nesting, or any
 * shape the canvas reports as "unsupported".
 *
 * The Accordion auto-opens when the canvas reports it cannot render
 * the current shape so the user is not stranded -- the canvas's
 * "Open Advanced view" button calls into the same setter.
 */
function CanvasAndAdvanced({
  tree,
  selectedNodeId,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  sandboxBadge,
}: Pick<
  Props,
  | "selectedNodeId"
  | "onSelectNode"
  | "onUpdate"
  | "onRequestAdd"
  | "onRequestCoach"
  | "sandboxBadge"
> & { tree: EditableLogicNode }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  return (
    <Box sx={{ minWidth: 0 }}>
      <SentenceCanvas
        tree={tree}
        selectedNodeId={selectedNodeId}
        onSelectNode={onSelectNode}
        onUpdate={onUpdate}
        onRequestAdd={onRequestAdd}
        onRequestCoach={onRequestCoach}
        onOpenAdvancedView={() => setAdvancedOpen(true)}
        sandboxBadge={sandboxBadge}
      />
      <Accordion
        expanded={advancedOpen}
        onChange={(_e, expanded) => setAdvancedOpen(expanded)}
        sx={{
          mt: 2,
          boxShadow: "none",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1.5,
          "&:before": { display: "none" },
          bgcolor: "grey.50",
        }}
      >
        <AccordionSummary
          expandIcon={<ExpandMoreIcon fontSize="small" />}
          aria-label={CANVAS_CARDS.advancedAccordionTitle}
          sx={{ minHeight: 44, "& .MuiAccordionSummary-content": { my: 0.75 } }}
        >
          <Box>
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, color: "text.primary" }}
            >
              {CANVAS_CARDS.advancedAccordionTitle}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", lineHeight: 1.4 }}
            >
              {CANVAS_CARDS.advancedAccordionHint}
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0 }}>
          <LogicTreeEditor
            root={tree}
            selectedNodeId={selectedNodeId}
            onSelect={onSelectNode}
            onUpdate={onUpdate}
            onRequestAdd={onRequestAdd}
            onRequestCoach={onRequestCoach}
          />
        </AccordionDetails>
      </Accordion>
    </Box>
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

/**
 * Friendly empty state shown when the rule has no children. A
 * first-time reviewer should never see a blank canvas with no
 * obvious next action; this gives them one short sentence and a
 * primary CTA they can click to start.
 */
function EmptyTreeState({
  onAddFirstSymptom,
}: {
  onAddFirstSymptom: (anchor: HTMLElement) => void;
}) {
  return (
    <Box
      role="status"
      aria-label="This rule is empty"
      sx={{
        p: 3,
        borderRadius: 2,
        border: "1px dashed",
        borderColor: "divider",
        bgcolor: "grey.50",
        textAlign: "center",
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
        sx={{
          borderRadius: 999,
          textTransform: "none",
          fontWeight: 600,
          px: 2.5,
        }}
      >
        Add the first symptom
      </Button>
    </Box>
  );
}
