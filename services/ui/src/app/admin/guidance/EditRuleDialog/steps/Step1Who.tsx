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

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";

import LogicTreeEditor from "../LogicTreeEditor";
import { STEP_HELPERS, STEP_TITLES } from "../copy";
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
}: Props) {
  const treeIsEmpty =
    !tree ||
    !Array.isArray(tree.children) ||
    tree.children.length === 0;

  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <StepHeader />

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
              This rule has{" "}
              <strong>{duplicates.length} repeated symptom sets</strong>.
              Removing duplicates keeps the rule easier to read.
            </>
          )}
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
        <Box sx={{ minWidth: 0 }}>
          {tree && (
            <LogicTreeEditor
              root={tree}
              selectedNodeId={selectedNodeId}
              onSelect={onSelectNode}
              onUpdate={onUpdate}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
            />
          )}
        </Box>
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
