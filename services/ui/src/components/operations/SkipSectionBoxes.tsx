/**
 * Read-only list of the tick boxes LEO found in a skipped section.
 *
 * Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import type { FormSchemaSection } from "./formSchemaDetector";

const SKIP_SECTION_TYPES = new Set(["admin", "template_noise"]);

export function SkipSectionBoxes({ section }: { section: FormSchemaSection }) {
  const labels = SKIP_SECTION_TYPES.has(section.section_type)
    ? section.items.map((item) => item.pattern).filter((label) => label.trim())
    : [];
  if (!labels.length) return null;
  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        Tick boxes in this section. LEO skips these, so they never become
        patient facts. They help LEO know this form.
      </Typography>
      <Box
        component="ul"
        aria-label="Tick boxes in this section"
        sx={{ m: 0, mt: 0.5, pl: 2.5, typography: "caption" }}
      >
        {labels.map((label) => (
          <li key={label}>{label}</li>
        ))}
      </Box>
    </Box>
  );
}
