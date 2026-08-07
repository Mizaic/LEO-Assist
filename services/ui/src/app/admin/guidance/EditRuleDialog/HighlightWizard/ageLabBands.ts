/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-E5B04297
 *   DO: DO-C38E6184
 *   VT: VT-409A9A74
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-E5B04297")
 *
 * Build OR(AND(age range, observation threshold)) trees for table-driven
 * NICE rules (NG12 CA125 / PSA age bands).
 */

import { freshNodeId, mintPathwayKey } from "../treeOps";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  ObservationOperator,
} from "../types";

export interface AgeLabBandRow {
  ageFrom: string;
  ageTo: string;
  value: string;
}

export interface AgeLabBandSpec {
  observableId: string;
  observableTerm: string;
  unit: string;
  operator: ObservationOperator;
  bands: AgeLabBandRow[];
}

export const DEFAULT_AGE_LAB_BANDS: AgeLabBandRow[] = [
  { ageFrom: "40", ageTo: "49", value: "" },
  { ageFrom: "50", ageTo: "59", value: "" },
  { ageFrom: "60", ageTo: "69", value: "" },
  { ageFrom: "70", ageTo: "", value: "" },
];

function parseNum(raw: string): number | null {
  const trimmed = String(raw).trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function bandRowErrors(row: AgeLabBandRow): string | null {
  const from = parseNum(row.ageFrom);
  if (from === null || from < 0) return "Each band needs a valid age from.";
  const toRaw = row.ageTo.trim();
  if (toRaw !== "") {
    const to = parseNum(row.ageTo);
    if (to === null || to < from) return "Age to must be blank or at least age from.";
  }
  const value = parseNum(row.value);
  if (value === null) return "Each band needs a lab value.";
  return null;
}

export function validateAgeLabBandSpec(spec: AgeLabBandSpec): string | null {
  if (!spec.observableId.trim()) return "Pick a lab reading (observable).";
  if (!spec.unit.trim()) return "Enter a unit (for example ug/L or IU/ml).";
  if (spec.bands.length === 0) return "Add at least one age band.";
  for (const row of spec.bands) {
    const err = bandRowErrors(row);
    if (err) return err;
  }
  return null;
}

export function bandSummaryText(
  row: AgeLabBandRow,
  observableTerm: string,
  operator: ObservationOperator,
  unit: string,
): string {
  const from = parseNum(row.ageFrom) ?? 0;
  const toRaw = row.ageTo.trim();
  const value = parseNum(row.value) ?? 0;
  const ageLabel =
    toRaw === ""
      ? `is ${from} years or older`
      : `is between ${from} and ${parseNum(row.ageTo)} years`;
  const opLabel =
    operator === ">="
      ? "at least"
      : operator === ">"
        ? "more than"
        : operator === "<="
          ? "at most"
          : operator === "<"
            ? "less than"
            : "exactly";
  const term = observableTerm.trim() || "lab reading";
  return `${ageLabel}, ${term} ${opLabel} ${value} ${unit}`.trim();
}

function ageNode(row: AgeLabBandRow): EditableLogicNode {
  const from = parseNum(row.ageFrom)!;
  const toRaw = row.ageTo.trim();
  if (toRaw === "") {
    return {
      node_id: freshNodeId(),
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: ">=",
      value: String(from),
      unit: "years",
    };
  }
  const to = parseNum(row.ageTo)!;
  return {
    node_id: freshNodeId(),
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: "between",
    value: String(from),
    value2: String(to),
    unit: "years",
  };
}

function observationNode(
  spec: AgeLabBandSpec,
  row: AgeLabBandRow,
): EditableLogicNode {
  const observation: EditableObservationPayload = {
    kind: "OBSERVATION",
    observable_id: spec.observableId,
    observable_term: spec.observableTerm,
    operator: spec.operator,
    value: parseNum(row.value)!,
    unit: spec.unit.trim(),
    within_days: 365,
  };
  return {
    node_id: freshNodeId(),
    kind: "OBSERVATION",
    observation,
  };
}

/** OR of AND(age, observation) pathways -- CA125 / PSA table shape. */
export function buildAgeLabBandTree(spec: AgeLabBandSpec): EditableLogicNode {
  const err = validateAgeLabBandSpec(spec);
  if (err) throw new Error(err);
  const children = spec.bands.map((row) => ({
    node_id: freshNodeId(),
    kind: "AND" as const,
    pathway_key: mintPathwayKey(),
    children: [ageNode(row), observationNode(spec, row)],
  }));
  return {
    node_id: freshNodeId(),
    kind: "OR",
    children,
  };
}
