/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Step 3 band for age/sex that apply to ONE situation only.
 * Leaves attach under the pathway AND (never the pathway OR).
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";

import DemographicRow from "../LogicTreeEditor/DemographicRow";
import type { EditableLogicNode, NodeUpdate } from "../types";
import { STEP_PATHWAY_CONDITIONS } from "./copy";

export type PathwayDemographicField = "age" | "sex";

interface Props {
  demographics: EditableLogicNode[];
  onAdd: (field: PathwayDemographicField) => void;
  onUpdate: (update: NodeUpdate) => void;
}

function hasField(
  demographics: EditableLogicNode[],
  field: PathwayDemographicField,
): boolean {
  return demographics.some((d) => d.kind === "DEMOGRAPHIC" && d.field === field);
}

export default function PathwayDemographicsPanel({
  demographics,
  onAdd,
  onUpdate,
}: Props) {
  const hasAge = hasField(demographics, "age");
  const hasSex = hasField(demographics, "sex");

  return (
    <Box
      data-testid="pathway-demographics-panel"
      sx={{
        p: 1.5,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "grey.50",
      }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.25 }}>
        {STEP_PATHWAY_CONDITIONS.demographicsHeading}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
        {STEP_PATHWAY_CONDITIONS.demographicsHelper}
      </Typography>

      {demographics.length > 0 && (
        <Stack spacing={0.75} sx={{ mb: 1.25 }} data-testid="pathway-demographic-rows">
          {demographics.map((node) => (
            <DemographicRow key={node.node_id} node={node} onUpdate={onUpdate} />
          ))}
        </Stack>
      )}

      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddRoundedIcon fontSize="small" />}
          disabled={hasAge}
          onClick={() => onAdd("age")}
          aria-label={STEP_PATHWAY_CONDITIONS.addAgeAriaLabel}
        >
          {STEP_PATHWAY_CONDITIONS.addAgeLabel}
        </Button>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddRoundedIcon fontSize="small" />}
          disabled={hasSex}
          onClick={() => onAdd("sex")}
          aria-label={STEP_PATHWAY_CONDITIONS.addSexAriaLabel}
        >
          {STEP_PATHWAY_CONDITIONS.addSexLabel}
        </Button>
      </Stack>
    </Box>
  );
}

/** Direct DEMOGRAPHIC children of a pathway AND (not nested clusters). */
export function pathwayDemographicChildren(
  pathwayNode: EditableLogicNode,
): EditableLogicNode[] {
  return (pathwayNode.children ?? []).filter((c) => c.kind === "DEMOGRAPHIC");
}
