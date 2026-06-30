"use client";
/**
 * Dashed-border add buttons for a group body.
 * Three actions: symptom/sign, patient detail, lab value.
 * Always visible -- not hidden behind hover.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import AddIcon from "@mui/icons-material/Add";

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
}

export default function AddBar({
  onAddConcept,
  onAddDemographic,
  onAddObservation,
  onAddRuleFired,
}: Props) {
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 1.25, flexWrap: "wrap", rowGap: 0.75 }}>
      <Button
        startIcon={<AddIcon sx={{ fontSize: 14 }} />}
        size="small"
        variant="outlined"
        sx={dashedBtnSx}
        onClick={(e) => onAddConcept(e.currentTarget)}
        aria-label="Add a symptom or sign"
      >
        Add symptom or sign
      </Button>
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
      {onAddObservation && (
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
      )}
      {onAddRuleFired && (
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
      )}
    </Stack>
  );
}
