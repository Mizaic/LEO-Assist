/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
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
  counts?: Record<string, number>;
}

function MultiChipSelect({ label, options, selected, onChange, counts }: MultiChipProps) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  const visibleOptions = counts
    ? options.filter((opt) => (counts[opt.value] ?? 0) > 0)
    : options;

  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        {label}
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
        {visibleOptions.map((opt) => {
          const count = counts?.[opt.value];
          const chipLabel = count != null ? `${opt.label} (${count})` : opt.label;
          return (
            <Chip
              key={opt.value}
              label={chipLabel}
              size="small"
              variant={selected.includes(opt.value) ? "filled" : "outlined"}
              color={selected.includes(opt.value) ? "primary" : "default"}
              onClick={() => toggle(opt.value)}
              sx={{ fontSize: "0.7rem" }}
            />
          );
        })}
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
  cancerTypeCounts?: Record<string, number>;
}

export default function PathwayFilterChips({
  pathwayFilter,
  cancerTypes,
  closureReasons,
  onCancerTypesChange,
  onClosureReasonsChange,
  cancerTypeCounts,
}: Props) {
  if (pathwayFilter === "confirmed") {
    return (
      <MultiChipSelect
        label="Cancer type"
        options={CANCER_TYPE_OPTIONS}
        selected={cancerTypes}
        onChange={onCancerTypesChange}
        counts={cancerTypeCounts}
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
