/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A0ADDB38
 *   DI: DI-EB716E68
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")
 */
"use client";

/**
 * Variants step for Validation Lab brainstorm drawer.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { ScenarioVariant } from "./scenarioVariants";

function triggerChip(variant: ScenarioVariant): {
  label: string;
  color: "default" | "success" | "warning";
} {
  if (variant.expectedTrigger === true) {
    return { label: "Rule should fire", color: "success" };
  }
  if (variant.expectedTrigger === false) {
    return { label: "Rule should not fire", color: "warning" };
  }
  const reason = String(variant.expectedTriggerReason || "").toLowerCase();
  if (reason.includes("not currently compiled")) {
    return { label: "Rule not compiled yet", color: "default" };
  }
  if (reason.includes("unavailable") || reason.includes("could not check")) {
    return { label: "Could not check rule", color: "default" };
  }
  if (reason.includes("no recommendation")) {
    return { label: "Freeform (no rule check)", color: "default" };
  }
  return { label: "Trigger not checked against a rule", color: "default" };
}

function patientSummary(variant: ScenarioVariant): string {
  const parts: string[] = [];
  if (variant.patientAge) parts.push(`age ${variant.patientAge}`);
  if (variant.patientSex) parts.push(String(variant.patientSex));
  if (variant.patientName) parts.push(variant.patientName);
  return parts.length ? parts.join(" · ") : "Demographics not set";
}

function pmhSummary(variant: ScenarioVariant): string {
  const terms = (variant.pmh || [])
    .map((row) => row.term || row.conceptId)
    .filter(Boolean);
  if (!terms.length) return "";
  return terms.slice(0, 4).join(", ") + (terms.length > 4 ? "…" : "");
}

interface Props {
  variants: ScenarioVariant[];
  selectedIds: Set<string>;
  selectedCount: number;
  guidance: string;
  busy: boolean;
  onToggle: (variantId: string) => void;
  onRetry: () => void;
  onCreate: () => void;
}

export default function ScenarioBrainstormVariantsStep({
  variants,
  selectedIds,
  selectedCount,
  guidance,
  busy,
  onToggle,
  onRetry,
  onCreate,
}: Props) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2" component="h6">
        Variants
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Choose which synthetic patients to create. Each card is one test case.
        With attached recommendations, expect about 3 variants per
        recommendation.
      </Typography>
      {variants.length === 0 ? (
        <Alert
          severity="warning"
          data-testid="brainstorm-empty-variants"
          action={
            <Button
              color="inherit"
              size="small"
              disabled={busy}
              onClick={onRetry}
            >
              Retry
            </Button>
          }
        >
          {guidance ||
            "No test cases were generated. Retry, or go back and narrow the scenario."}
        </Alert>
      ) : null}
      {variants.map((v) => {
        const trigger = triggerChip(v);
        const pmh = pmhSummary(v);
        return (
          <Box
            key={v.variantId}
            sx={{
              border: "1px solid",
              borderColor: "divider",
              p: 1.25,
              borderRadius: 1,
            }}
          >
            <FormControlLabel
              control={
                <Checkbox
                  checked={selectedIds.has(v.variantId)}
                  onChange={() => onToggle(v.variantId)}
                  inputProps={{
                    "aria-label": `Select ${v.label}`,
                  }}
                />
              }
              label={
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  {v.label}
                </Typography>
              }
            />
            {v.summary ? (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ ml: 4 }}
                data-testid={`brainstorm-variant-summary-${v.variantId}`}
              >
                {v.summary}
              </Typography>
            ) : null}
            <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
              {v.rationale}
            </Typography>
            <Typography variant="caption" display="block" sx={{ ml: 4, mt: 0.5 }}>
              {patientSummary(v)}
            </Typography>
            {pmh ? (
              <Typography variant="caption" display="block" sx={{ ml: 4 }}>
                History: {pmh}
              </Typography>
            ) : null}
            {v.targetRecId ? (
              <Typography variant="caption" display="block" sx={{ ml: 4 }}>
                Tests recommendation: {v.targetRecId}
              </Typography>
            ) : null}
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ mt: 0.75, ml: 4 }}
              flexWrap="wrap"
              useFlexGap
            >
              {v.recommended ? (
                <Chip
                  key={`${v.variantId}-rec`}
                  size="small"
                  color="primary"
                  label="recommended"
                />
              ) : null}
              {v.isControl ? (
                <Chip
                  key={`${v.variantId}-ctrl`}
                  size="small"
                  label="control"
                />
              ) : null}
              <Chip
                key={`${v.variantId}-trigger`}
                size="small"
                color={trigger.color}
                label={trigger.label}
              />
              {(v.tags || []).map((tag) => (
                <Chip
                  key={`${v.variantId}-tag-${tag}`}
                  size="small"
                  variant="outlined"
                  label={tag}
                />
              ))}
            </Stack>
          </Box>
        );
      })}
      <Button
        variant="contained"
        disabled={busy || selectedCount === 0}
        onClick={onCreate}
      >
        {busy ? <CircularProgress size={18} /> : `Create ${selectedCount}`}
      </Button>
    </Stack>
  );
}
