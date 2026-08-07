/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387
 *   DO: DO-AA74E9A6
 *   VT: VT-5632FA0D
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-C21AE387")
 */
"use client";

/**
 * Unit dropdown backed by LabResultConfig conversions (unit converter).
 * Falls back to the seeded UCUM list when no lab config exists.
 */
import { useEffect, useState } from "react";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";

import { getLabResultConfig } from "@/app/admin/lab-results/api";
import type { LabResultConfig } from "@/app/admin/lab-results/types";

import {
  preferredUnit,
  unitOptionsForObservable,
} from "./observableUnits";

interface Props {
  observableId?: string | null;
  value: string;
  onChange: (unit: string) => void;
  ariaLabel: string;
  /** When true and value is blank, set canonical unit from lab config. */
  autoFillCanonical?: boolean;
  minWidth?: number;
}

export default function ObservableUnitSelect({
  observableId,
  value,
  onChange,
  ariaLabel,
  autoFillCanonical = true,
  minWidth = 110,
}: Props) {
  const [config, setConfig] = useState<LabResultConfig | null>(null);

  useEffect(() => {
    const id = String(observableId ?? "").trim();
    if (!id) {
      setConfig(null);
      return;
    }
    let cancelled = false;
    getLabResultConfig(id)
      .then((res) => {
        if (!cancelled) setConfig(res.item ?? null);
      })
      .catch(() => {
        if (!cancelled) setConfig(null);
      });
    return () => {
      cancelled = true;
    };
  }, [observableId]);

  useEffect(() => {
    if (!autoFillCanonical) return;
    if (String(value ?? "").trim()) return;
    const preferred =
      preferredUnit(config) || unitOptionsForObservable(config)[0] || "";
    if (preferred) onChange(preferred);
  }, [autoFillCanonical, config, onChange, value]);

  const options = unitOptionsForObservable(config, value);
  const selectValue = String(value ?? "").trim();
  const safeValue =
    selectValue && options.includes(selectValue)
      ? selectValue
      : options[0] ?? "";

  return (
    <Select
      size="small"
      value={safeValue}
      displayEmpty
      onChange={(e) => onChange(String(e.target.value))}
      inputProps={{ "aria-label": ariaLabel }}
      sx={{ minWidth }}
    >
      {options.map((unit) => (
        <MenuItem key={unit} value={unit}>
          {unit}
        </MenuItem>
      ))}
    </Select>
  );
}
