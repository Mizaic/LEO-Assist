"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Inline-text replacement for LogicTreeEditor/AddBar.tsx's dashed
 * buttons: "+ add another symptom" / "+ add a patient detail" / etc.
 * as underlined inline links continuing the sentence, wired to the
 * exact same add handlers AddBar already takes so both canvases stay
 * behaviourally identical.
 */
import Box from "@mui/material/Box";

interface Props {
  onAddConcept: (anchor?: HTMLElement | null) => void;
  onAddDemographic?: () => void;
  onAddObservation?: () => void;
  onAddRuleFired?: () => void;
  /** Adds a nested sub-group (for example "any of these" inside an
   *  "all of these" pathway) as a new child of the current group. */
  onAddGroup?: () => void;
  /** Adds a nested "patient should not have" group (logic kind NOT). */
  onAddShouldNotHave?: () => void;
  /** Pure-CONCEPT AT_LEAST clusters only ever accept more concepts
   *  (matching InlineAtLeast's single "Add" Chip in GroupBody.tsx), so
   *  every other add-link is suppressed regardless of which handlers
   *  are passed in. */
  onlyConcept?: boolean;
  /** Override the concept link's visible text and aria-label -- used by
   *  EmptySentenceState.tsx, which says "add the first symptom" instead
   *  of "add another symptom" since there is nothing in the rule yet. */
  conceptLabel?: string;
  conceptAriaLabel?: string;
}

const linkSx = {
  cursor: "pointer",
  color: "primary.main",
  fontWeight: 600,
  fontSize: "0.8rem",
  fontFamily: "inherit",
  textDecoration: "underline",
  textDecorationStyle: "dashed",
  textUnderlineOffset: "3px",
  background: "none",
  border: "none",
  padding: 0,
  whiteSpace: "nowrap",
  "&:hover": { color: "primary.dark" },
} as const;

export default function AddInlineLinks({
  onAddConcept,
  onAddDemographic,
  onAddObservation,
  onAddRuleFired,
  onAddGroup,
  onAddShouldNotHave,
  onlyConcept,
  conceptLabel = "+ add another symptom",
  conceptAriaLabel = "Add a symptom, sign, procedure, or situation",
}: Props) {
  return (
    <Box
      component="span"
      sx={{ display: "inline-flex", flexWrap: "wrap", gap: 1.25, alignItems: "center" }}
    >
      <Box
        component="button"
        type="button"
        sx={linkSx}
        onClick={(e) => onAddConcept(e.currentTarget)}
        aria-label={conceptAriaLabel}
      >
        {conceptLabel}
      </Box>
      {onAddDemographic && !onlyConcept && (
        <Box
          component="button"
          type="button"
          sx={linkSx}
          onClick={onAddDemographic}
          aria-label="Add a patient detail"
        >
          + add a patient detail
        </Box>
      )}
      {onAddObservation && !onlyConcept && (
        <Box
          component="button"
          type="button"
          sx={linkSx}
          onClick={onAddObservation}
          aria-label="Add a lab value or reading"
        >
          + add a lab value
        </Box>
      )}
      {onAddRuleFired && !onlyConcept && (
        <Box
          component="button"
          type="button"
          sx={linkSx}
          onClick={onAddRuleFired}
          aria-label="Add a rule dependency"
        >
          + add a rule dependency
        </Box>
      )}
      {onAddGroup && !onlyConcept && (
        <Box
          component="button"
          type="button"
          sx={linkSx}
          onClick={onAddGroup}
          aria-label="Add a condition group, for example a set of options where any one match is enough"
        >
          + add a condition group
        </Box>
      )}
      {onAddShouldNotHave && !onlyConcept && (
        <Box
          component="button"
          type="button"
          sx={linkSx}
          onClick={onAddShouldNotHave}
          aria-label="Add things the patient should not have"
        >
          + patient should not have
        </Box>
      )}
    </Box>
  );
}
