"use client";
/**
 * Dashed-border add buttons for a group body.
 * Actions: symptom/sign/procedure/situation, patient detail, lab value,
 * rule dependency, and a nested AND/OR/NOT/at-least sub-group. Always
 * visible -- not hidden behind hover.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { motion as fm } from "framer-motion";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import AddIcon from "@mui/icons-material/Add";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";

import { useMotion } from "@leo/design-system";

import { bounceInteraction } from "../../motionPresets";

const dashedBtnSx = {
  border: "1.5px dashed",
  borderColor: "divider",
  borderRadius: 1.5,
  textTransform: "none",
  fontSize: "0.78rem",
  fontWeight: 500,
  color: "text.secondary",
  bgcolor: "transparent",
  py: 0.5,
  px: 1.25,
  minHeight: 32,
  "&:hover": {
    borderColor: "primary.main",
    color: "primary.main",
    bgcolor: "primary.50",
  },
} as const;

interface Props {
  onAddConcept: (anchor?: HTMLElement | null) => void;
  onAddDemographic: () => void;
  onAddObservation?: () => void;
  onAddRuleFired?: () => void;
  /** Adds a nested sub-group (for example "any of these" inside an
   *  "all of these" pathway) as a new child of the current group. */
  onAddGroup?: () => void;
  /** Adds a nested "patient should not have" group (logic kind NOT). */
  onAddShouldNotHave?: () => void;
}

export default function AddBar({
  onAddConcept,
  onAddDemographic,
  onAddObservation,
  onAddRuleFired,
  onAddGroup,
  onAddShouldNotHave,
}: Props) {
  const { reducedMotion } = useMotion();
  const spring = bounceInteraction(reducedMotion);

  return (
    <Stack direction="row" spacing={1} sx={{ mt: 1.25, flexWrap: "wrap", rowGap: 0.75 }}>
      <fm.div style={{ display: "inline-flex" }} {...spring}>
        <Button
          startIcon={<AddIcon sx={{ fontSize: 14 }} />}
          size="small"
          variant="outlined"
          sx={dashedBtnSx}
          onClick={(e) => onAddConcept(e.currentTarget)}
          aria-label="Add a symptom, sign, procedure, or situation"
        >
          Add symptom, procedure, or situation
        </Button>
      </fm.div>
      <fm.div style={{ display: "inline-flex" }} {...spring}>
        <Button
          startIcon={<AddIcon sx={{ fontSize: 14 }} />}
          size="small"
          variant="outlined"
          sx={dashedBtnSx}
          onClick={onAddDemographic}
          aria-label="Add a patient detail"
        >
          Add patient detail
        </Button>
      </fm.div>
      {onAddObservation && (
        <fm.div style={{ display: "inline-flex" }} {...spring}>
          <Button
            startIcon={<AddIcon sx={{ fontSize: 14 }} />}
            size="small"
            variant="outlined"
            sx={dashedBtnSx}
            onClick={onAddObservation}
            aria-label="Add a lab value or reading"
          >
            Add lab value
          </Button>
        </fm.div>
      )}
      {onAddRuleFired && (
        <fm.div style={{ display: "inline-flex" }} {...spring}>
          <Button
            startIcon={<AddIcon sx={{ fontSize: 14 }} />}
            size="small"
            variant="outlined"
            sx={dashedBtnSx}
            onClick={onAddRuleFired}
            aria-label="Add a rule dependency"
          >
            Add rule dependency
          </Button>
        </fm.div>
      )}
      {onAddGroup && (
        <fm.div style={{ display: "inline-flex" }} {...spring}>
          <Button
            startIcon={<AccountTreeOutlinedIcon sx={{ fontSize: 14 }} />}
            size="small"
            variant="outlined"
            sx={dashedBtnSx}
            onClick={onAddGroup}
            aria-label="Add a condition group, for example a set of options where any one match is enough"
          >
            Add condition group
          </Button>
        </fm.div>
      )}
      {onAddShouldNotHave && (
        <fm.div style={{ display: "inline-flex" }} {...spring}>
          <Button
            startIcon={<BlockOutlinedIcon sx={{ fontSize: 14 }} />}
            size="small"
            variant="outlined"
            sx={dashedBtnSx}
            onClick={onAddShouldNotHave}
            aria-label="Add things the patient should not have"
          >
            Patient should not have
          </Button>
        </fm.div>
      )}
    </Stack>
  );
}
