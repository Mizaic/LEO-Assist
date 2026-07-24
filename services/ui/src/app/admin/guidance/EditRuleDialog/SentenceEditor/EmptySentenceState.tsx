"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Prose-style empty state for the Simple sentence canvas: "This rule
 * doesn't check anything yet." followed by the same inline add-links
 * AddInlineLinks already uses inside a group, so the very first thing
 * a reviewer sees in Simple mode already looks like the sentence
 * they're about to build. Replaces Step1Who.tsx's boxed EmptyTreeState
 * when the view mode is "simple"; wired to the exact same
 * onAddFirstSymptom / onAddFirstDemographic / onAddFirstObservation
 * handlers so the empty-state CTAs behave identically either way.
 */
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";

import AIDraftButton from "../AIDraftButton";
import type { EditableLogicNode } from "../types";
import AddInlineLinks from "./AddInlineLinks";

interface Props {
  onAddFirstSymptom: (anchor: HTMLElement) => void;
  onAddFirstDemographic?: () => void;
  onAddFirstObservation?: () => void;
  ruleId?: string;
  onAIDraft?: (tree: EditableLogicNode) => void;
}

export default function EmptySentenceState({
  onAddFirstSymptom,
  onAddFirstDemographic,
  onAddFirstObservation,
  ruleId,
  onAIDraft,
}: Props) {
  return (
    <Box
      role="status"
      aria-label="This rule is empty"
      sx={{
        p: 3, borderRadius: 2,
        border: "1px dashed", borderColor: "divider",
        bgcolor: "grey.50",
      }}
    >
      <Typography variant="body1" sx={{ color: "text.primary", lineHeight: 1.7 }}>
        This rule doesn&rsquo;t check anything yet.{" "}
        <AddInlineLinks
          conceptLabel="+ add the first symptom"
          conceptAriaLabel="Add the first symptom, sign, procedure, or situation to this rule"
          onAddConcept={(anchor) => {
            if (anchor) onAddFirstSymptom(anchor);
          }}
          onAddDemographic={onAddFirstDemographic}
          onAddObservation={onAddFirstObservation}
        />
      </Typography>

      {ruleId && onAIDraft && (
        <>
          <Divider sx={{ my: 2 }}>or let AI draft it</Divider>
          <AIDraftButton ruleId={ruleId} onDraft={onAIDraft} variant="primary-cta" />
        </>
      )}
    </Box>
  );
}
