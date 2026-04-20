/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Tab 1 -- output schema editor. Extracted from prompts/[id]/page.tsx
 * (Phase 4b decomposition).
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import SchemaBuilder from "@/components/schema-builder/SchemaBuilder";

interface OutputFormatTabProps {
  outputSchema: string;
  onChange: (next: string) => void;
}

export function OutputFormatTab({
  outputSchema,
  onChange,
}: OutputFormatTabProps) {
  return (
    <Box sx={{ pt: 2 }}>
      <Alert severity="info" sx={{ mb: 2.5 }} icon={<InfoOutlinedIcon />}>
        <Typography variant="body2" fontWeight={600} gutterBottom>
          This defines what the AI must output
        </Typography>
        <Typography variant="body2">
          Stored separately from the instructions and automatically appended
          at runtime. The no-code pipeline builder reads this to understand
          what fields flow out of this step. Switch to JSON view if you need
          to edit the raw schema.
        </Typography>
      </Alert>

      <SchemaBuilder value={outputSchema} onChange={onChange} />
    </Box>
  );
}
