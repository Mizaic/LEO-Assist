"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { CANCER_TYPE_OPTIONS, CLOSURE_REASON_OPTIONS } from "@/lib/pathwayLabels";

interface MultiChipProps {
  label: string;
  options: Array<{ value: string; label: string }>;
  selected: string[];
  onChange: (next: string[]) => void;
}

function MultiChipSelect({ label, options, selected, onChange }: MultiChipProps) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        {label}
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
        {options.map((opt) => (
          <Chip
            key={opt.value}
            label={opt.label}
            size="small"
            variant={selected.includes(opt.value) ? "filled" : "outlined"}
            color={selected.includes(opt.value) ? "primary" : "default"}
            onClick={() => toggle(opt.value)}
            sx={{ fontSize: "0.7rem" }}
          />
        ))}
      </Box>
    </Box>
  );
}

interface Props {
  pathwayFilter: "confirmed" | "closures" | "all";
  cancerTypes: string[];
  closureReasons: string[];
  onCancerTypesChange: (v: string[]) => void;
  onClosureReasonsChange: (v: string[]) => void;
}

export default function PathwayFilterChips({
  pathwayFilter,
  cancerTypes,
  closureReasons,
  onCancerTypesChange,
  onClosureReasonsChange,
}: Props) {
  if (pathwayFilter === "confirmed") {
    return (
      <MultiChipSelect
        label="Cancer type"
        options={CANCER_TYPE_OPTIONS}
        selected={cancerTypes}
        onChange={onCancerTypesChange}
      />
    );
  }

  if (pathwayFilter === "closures") {
    return (
      <MultiChipSelect
        label="Closure reason"
        options={CLOSURE_REASON_OPTIONS}
        selected={closureReasons}
        onChange={onClosureReasonsChange}
      />
    );
  }

  return null;
}
